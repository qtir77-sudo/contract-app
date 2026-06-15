#!/usr/bin/env python3
"""Main server v2 - Contract + NHS pe acelasi port"""
import os, sys, json, importlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))

# ── Patch contract module ─────────────────────────────────────────────────────
import completeaza_contract as _cm
_cm.DIR             = DIR
_cm.PDF_SOURCE      = DIR / "test_contract_saca.pdf"
_cm.RECEIPT_PDF     = DIR / "adaugare_ppayscript.pdf"
_cm.BRITISH_GAS_PDF = DIR / "british_gas_statement.pdf"
_cm.NI_LETTER_PDF   = DIR / "ni_letter.pdf"

# ── Patch NHS module ──────────────────────────────────────────────────────────
import completeaza_nhs as _nm
_nm.DIR        = DIR
_nm.PDF_SOURCE = DIR / "CHIMEZIE_GERALD_OKEUGBO_GP.pdf"
_nm.PDF_ANNEX  = DIR / "British_Gasolineeeeeee.pdf"
_nm.BOLD_FONTS = [
    str(DIR / "arial_bold.ttf"),
    str(DIR / "arimo_bold.ttf"),
    str(DIR / "ni_bold_font.ttf"),
]

VERSION = "2.0"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): return

    def _send(self, code, body, ct, dl=None):
        if isinstance(body, str):
            body = body.encode()
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
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        # NHS GP search
        if path == "/find-gp":
            city = (qs.get("city", [""])[0] or "").strip()
            try:
                gps = _nm.find_gps_overpass(city)
                self._send(200, json.dumps(gps, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, str(e), "text/plain")
            return

        # Proxy logo pentru contract tool
        if path == "/proxy-logo":
            url = (qs.get("url") or [""])[0]
            if not url.startswith("https://"):
                self._send(400, "bad url", "text/plain"); return
            try:
                import urllib.request, base64
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    b  = r.read()
                    ct = r.headers.get("Content-Type", "image/png").split(";")[0]
                self._send(200, json.dumps({"b64": f"data:{ct};base64,{base64.b64encode(b).decode()}"}), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}), "application/json")
            return

        # Serve static files
        if path in ("", "/"):
            path = "/index.html"

        fp = (DIR / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(DIR)) or not fp.is_file():
            self._send(404, "Not found", "text/plain"); return

        cmap = {".html": "text/html; charset=utf-8", ".css": "text/css",
                ".js": "application/javascript", ".png": "image/png",
                ".ttf": "font/ttf", ".pdf": "application/pdf"}
        body = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", cmap.get(fp.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def do_POST(self):
        path   = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length) if length else b"{}"

        try:
            data = json.loads(raw.decode())
        except Exception:
            self._send(400, "JSON invalid", "text/plain"); return

        # ── Contract PDF ──────────────────────────────────────────────────────
        if path == "/generate":
            try:
                pdf = _cm.fill_contract(data)
                self._send(200, pdf, "application/pdf", "contract-completat.pdf")
            except FileNotFoundError as e:
                self._send(404, str(e), "text/plain")
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send(500, f"Eroare: {e}", "text/plain")
            return

        # ── NHS Letter ────────────────────────────────────────────────────────
        if path == "/generate-nhs":
            try:
                pdf = _nm.fill_nhs_letter(data)
                self._send(200, pdf, "application/pdf", "nhs-registration.pdf")
            except FileNotFoundError as e:
                self._send(404, str(e), "text/plain")
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send(500, f"Eroare: {e}", "text/plain")
            return

        # ── Agent search ──────────────────────────────────────────────────────
        if path == "/search-agent":
            city = data.get("city", "").strip()
            if not city:
                self._send(400, json.dumps({"error": "Oras lipsa"}), "application/json"); return
            try:
                agents = _cm.search_real_agents(city)
                self._send(200, json.dumps({"agents": agents}), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}), "application/json")
            return

        self._send(404, "Not found", "text/plain")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    port = int(os.environ.get("PORT") or 8080)
    server = HTTPServer(("0.0.0.0", port), Handler)
    print("=" * 55)
    print(f"  DgoGPT Tools v{VERSION} — port {port}")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOprit.")

if __name__ == "__main__":
    main()
