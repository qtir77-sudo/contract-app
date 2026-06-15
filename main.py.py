#!/usr/bin/env python3
"""
Combined server v1.0
- /               -> index.html (taburi: Contract + NHS)
- /generate       -> Contract PDF
- /generate-nhs   -> NHS GP Letter PDF
- /search-agent   -> AI search agenti
- /find-gp        -> cautare GP Overpass
- /proxy-logo     -> proxy logo agent
"""
from __future__ import annotations
import json, sys, os, re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── Import logica din cele doua module ────────────────────────────────────────
# Adaugam DIR inainte de import ca amandoua modulele il folosesc
DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))

from completeaza_contract import fill_contract, search_real_agents, VERSION as CONTRACT_VERSION
from completeaza_nhs import fill_nhs_letter, find_gps_overpass, VERSION as NHS_VERSION

# Re-definim DIR dupa import ca modulele importate il pot suprascrie in namespace global
DIR = Path(__file__).resolve().parent

print(f"[START] Contract v{CONTRACT_VERSION} | NHS v{NHS_VERSION}")
print(f"[DIR] {DIR}")
print(f"[FILES] {list(DIR.iterdir())[:10]}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): return

    def _send(self, code, body, ct, dl=None):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        if dl:
            self.send_header("Content-Disposition", f'attachment; filename="{dl}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # ── /find-gp (NHS) ────────────────────────────────────────────────────
        if path == "/find-gp":
            qs = parse_qs(parsed.query)
            city = (qs.get("city", [""])[0] or "").strip()
            if not city:
                self._send(400, b"Missing city", "text/plain"); return
            try:
                gps = find_gps_overpass(city)
                self._send(200, json.dumps(gps, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, str(e).encode(), "text/plain")
            return

        # ── /proxy-logo (Contract) ────────────────────────────────────────────
        if path == "/proxy-logo":
            qs = parse_qs(parsed.query)
            url = (qs.get("url") or [""])[0]
            if not url.startswith("https://"):
                self._send(400, b"bad", "text/plain"); return
            try:
                import urllib.request, base64
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=8
                ) as r:
                    b = r.read()
                    ct = r.headers.get("Content-Type", "image/png").split(";")[0]
                self._send(200, json.dumps({"b64": f"data:{ct};base64,{base64.b64encode(b).decode()}"}).encode(), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return

        # ── Fisiere statice ───────────────────────────────────────────────────
        if path in ("", "/"):
            path = "/index.html"
        fp = (DIR / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(DIR)) or not fp.is_file():
            self._send(404, b"Not found", "text/plain"); return
        cmap = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".ttf": "font/ttf",
        }
        body = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", cmap.get(fp.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if fp.suffix == ".html":
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"

        # ── /generate (Contract) ─────────────────────────────────────────────
        if path == "/generate":
            try:
                data = json.loads(raw.decode())
            except Exception:
                self._send(400, b"JSON invalid", "text/plain"); return
            try:
                pdf = fill_contract(data)
            except FileNotFoundError as e:
                self._send(404, str(e).encode(), "text/plain"); return
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send(500, f"Eroare: {e}".encode(), "text/plain"); return
            self._send(200, pdf, "application/pdf", "contract-completat.pdf")
            return

        # ── /generate-nhs (NHS) ───────────────────────────────────────────────
        if path == "/generate-nhs":
            try:
                data = json.loads(raw.decode())
            except Exception:
                self._send(400, b"JSON invalid", "text/plain"); return
            try:
                pdf = fill_nhs_letter(data)
            except FileNotFoundError as e:
                self._send(404, str(e).encode(), "text/plain"); return
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send(500, f"Eroare: {e}".encode(), "text/plain"); return
            self._send(200, pdf, "application/pdf", "nhs-registration.pdf")
            return

        # ── /search-agent (Contract) ─────────────────────────────────────────
        if path == "/search-agent":
            try:
                body = json.loads(raw.decode())
                city = body.get("city", "").strip()
                if not city:
                    self._send(400, json.dumps({"error": "Oras lipsa"}).encode(), "application/json"); return
                self._send(200, json.dumps({"agents": search_real_agents(city)}).encode(), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return

        self._send(404, b"Not found", "text/plain")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8765))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print("=" * 60)
    print(f"  Combined Tool - Contract v{CONTRACT_VERSION} + NHS v{NHS_VERSION}")
    print(f"  Port: {port}")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOprit.")


if __name__ == "__main__":
    main()
