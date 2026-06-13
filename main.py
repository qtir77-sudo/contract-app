#!/usr/bin/env python3
"""Main server - ruleaza ambele tool-uri pe acelasi port"""
import os, sys, json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

DIR = Path(__file__).resolve().parent

# Import logica din ambele module
sys.path.insert(0, str(DIR))

# Patch paths in completeaza_contract
import completeaza_contract as contract_mod
contract_mod.PDF_SOURCE    = DIR / "test_contract_saca.pdf"
contract_mod.RECEIPT_PDF   = DIR / "adaugare_ppayscript.pdf"
contract_mod.BRITISH_GAS_PDF = DIR / "british_gas_statement.pdf"
contract_mod.NI_LETTER_PDF = DIR / "ni_letter.pdf"

import completeaza_nhs as nhs_mod
nhs_mod.PDF_SOURCE = DIR / "CHIMEZIE_GERALD_OKEUGBO_GP.pdf"
nhs_mod.PDF_ANNEX  = DIR / "British_Gasolineeeeeee.pdf"
nhs_mod.BOLD_FONTS = [
    str(DIR / "arial_bold.ttf"),
    str(DIR / "arimo_bold.ttf"),
]

VERSION = "6.0"

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
        from urllib.parse import parse_qs
        parsed = urlparse(self.path)
        path = parsed.path

        # NHS GP search
        if path == "/find-gp":
            qs = parse_qs(parsed.query)
            city = (qs.get("city", [""])[0] or "").strip()
            try:
                gps = nhs_mod.find_gps_overpass(city)
                self._send(200, json.dumps(gps).encode(), "application/json")
            except Exception as e:
                self._send(500, str(e).encode(), "text/plain")
            return

        # Proxy logo (contract tool)
        if path == "/proxy-logo":
            qs = parse_qs(parsed.query)
            url = (qs.get("url") or [""])[0]
            if not url.startswith("https://"):
                self._send(400, b"bad", "text/plain"); return
            try:
                import urllib.request, base64
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=8) as r:
                    b = r.read(); ct = r.headers.get("Content-Type", "image/png").split(";")[0]
                self._send(200, json.dumps({"b64": f"data:{ct};base64,{base64.b64encode(b).decode()}"}).encode(), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return

        # Serve files
        if path in ("", "/", "/contract", "/nhs"):
            path = "/index.html"

        fp = (DIR / path.lstrip("/")).resolve()
        if not str(fp).startswith(str(DIR)) or not fp.is_file():
            self._send(404, b"Not found", "text/plain"); return

        cmap = {".html": "text/html; charset=utf-8", ".css": "text/css",
                ".js": "application/javascript", ".png": "image/png"}
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
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"

        try:
            data = json.loads(raw.decode())
        except Exception:
            self._send(400, b"JSON invalid", "text/plain"); return

        if path == "/generate":
            try:
                pdf = contract_mod.fill_contract(data)
                self._send(200, pdf, "application/pdf", "contract-completat.pdf")
            except FileNotFoundError as e:
                self._send(404, str(e).encode(), "text/plain")
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send(500, f"Eroare: {e}".encode(), "text/plain")
            return

        if path == "/generate-nhs":
            try:
                pdf = nhs_mod.fill_nhs_letter(data)
                self._send(200, pdf, "application/pdf", "nhs-registration.pdf")
            except FileNotFoundError as e:
                self._send(404, str(e).encode(), "text/plain")
            except Exception as e:
                import traceback; traceback.print_exc()
                self._send(500, f"Eroare: {e}".encode(), "text/plain")
            return

        if path == "/search-agent":
            try:
                body = json.loads(raw.decode())
                city = body.get("city", "").strip()
                if not city:
                    self._send(400, json.dumps({"error": "Oras lipsa"}).encode(), "application/json"); return
                self._send(200, json.dumps({"agents": contract_mod.search_real_agents(city)}).encode(), "application/json")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return

        self._send(404, b"Not found", "text/plain")

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
    print(f"  DgoGPT Tool v{VERSION}")
    print(f"  Port: {port}")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOprit.")

if __name__ == "__main__":
    main()
