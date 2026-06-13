#!/usr/bin/env python3
"""NHS GP Registration Letter Tool v1.4 - Font identic cu originalul"""
from __future__ import annotations
import json, sys, webbrowser, os, tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
import fitz

DIR        = Path(__file__).resolve().parent
PDF_SOURCE = DIR / "CHIMEZIE_GERALD_OKEUGBO_GP.pdf"
PDF_ANNEX  = DIR / "British_Gasolineeeeeee.pdf"
VERSION    = "1.4"

BOLD_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    str(DIR / "arimo_bold.ttf"),
]

def _get_bold_font() -> str:
    for f in BOLD_FONTS:
        if os.path.exists(f):
            return f
    raise FileNotFoundError("Nu am gasit niciun font bold. Verifica ca arimo_bold.ttf e in folder.")

def _redact(page, x0, y0, x1, y1):
    page.add_redact_annot(fitz.Rect(x0, y0, x1, y1), fill=(1, 1, 1))
    page.apply_redactions()

def _wb(page, x, y, text, size, font_path):
    page.insert_text((x, y), text, fontfile=font_path, fontsize=size, color=(0, 0, 0))



def _patch_british_gas(src_path: str, dst_path: str, data: dict, font_path: str):
    """Inlocuieste numele si adresa din factura British Gas cu datele din formular."""
    name  = (data.get("patient_name")  or "").strip()
    addr1 = (data.get("patient_addr1") or "").strip()
    addr2 = (data.get("patient_addr2") or "").strip()
    addr3 = (data.get("patient_addr3") or "").strip()

    doc = fitz.open(src_path)
    page = doc[0]

    # Sterge toata zona cu numele si adresa originale - testat si verificat vizual
    # pdf_h=841.89, text la pdf_y=694.626 (L1) -> 648.501 (L4), font=12pt
    # fitz: y0 = (pdf_h - 694.626 - 11) = 136.3, y1 = (pdf_h - 648.501 + 5) = 198.4
    _redact(page, 35, 136.3, 335, 198.4)

    # Scrie noile date exact pe baseline-urile originale (testat vizual)
    # fitz_y = pdf_h - pdf_y -> [147.264, 162.639, 178.014, 193.389]
    y_coords = [147.264, 162.639, 178.014, 193.389]
    lines = [l for l in [name, addr1, addr2, addr3] if l]
    for i, line in enumerate(lines):
        if i < len(y_coords):
            page.insert_text((52.852, y_coords[i]), line,
                             fontfile=font_path, fontsize=12,
                             color=(0.2, 0.247059, 0.282353))

    doc.save(dst_path)
    doc.close()


def fill_nhs_letter(data: dict) -> bytes:
    if not PDF_SOURCE.is_file():
        raise FileNotFoundError(f"Nu gasesc PDF-ul sursa: {PDF_SOURCE}")

    font_path = _get_bold_font()
    print(f"[FONT] Folosesc: {font_path}")

    doc = fitz.open(PDF_SOURCE)
    page = doc[0]

    def wb(x, y, text, size=11.25):
        _wb(page, x, y, text, size, font_path)

    # 1. NUME + ADRESA PACIENT
    patient_name  = (data.get("patient_name")  or "").strip()
    patient_addr1 = (data.get("patient_addr1") or "").strip()
    patient_addr2 = (data.get("patient_addr2") or "").strip()
    patient_addr3 = (data.get("patient_addr3") or "").strip()

    _redact(page, 38, 148, 285, 208)
    lines = [l for l in [patient_name, patient_addr1, patient_addr2, patient_addr3] if l]
    y_pts = [161.8, 174.8, 186.8, 199.8]
    for i, line in enumerate(lines):
        if i < len(y_pts):
            wb(46.0, y_pts[i], line, 11.25)

    # 2. CABINET GP
    gp_name  = (data.get("gp_name")  or "").strip()
    gp_addr1 = (data.get("gp_addr1") or "").strip()
    gp_addr2 = (data.get("gp_addr2") or "").strip()
    gp_addr3 = (data.get("gp_addr3") or "").strip()

    _redact(page, 302, 178, 562, 248)
    gp_lines = [l for l in [gp_name, gp_addr1, gp_addr2, gp_addr3] if l]
    y_gp = [189.8, 207.3, 225.3, 239.8]
    sizes = [11.25, 12.0, 12.0, 12.0]
    for i, line in enumerate(gp_lines):
        if i < len(y_gp):
            wb(308.0, y_gp[i], line, sizes[i])

    # 3. RECEPTIE
    reception = (data.get("reception") or "").strip()
    if reception:
        _redact(page, 302, 287, 562, 308)
        wb(308.0, 301.1, f"Reception:{reception}", 12.0)

    # 4. DATA INREGISTRARII
    reg_date = (data.get("reg_date") or "").strip()
    if reg_date:
        _redact(page, 302, 316, 562, 334)
        wb(308.0, 330.1, f"Date of registration:{reg_date}", 12.0)

    # 5. NHS NUMBER
    nhs_no = (data.get("nhs_no") or "").strip()
    if nhs_no:
        _redact(page, 38, 314, 285, 334)
        wb(40.0, 328.1, f"NHS No. {nhs_no}", 12.0)

    # 6. DATA NASTERII
    dob = (data.get("dob") or "").strip()
    if dob:
        _redact(page, 38, 340, 285, 362)
        wb(39.0, 354.1, f"Your date of birth:{dob}", 12.0)

    # 7. DATA DOCUMENT
    _redact(page, 45, 370, 200, 388)

    # 8. MERGE CU BRITISH GAS - salveaza NHS pe disk temp, combina cu fitz
    if PDF_ANNEX.is_file():
        # Salveaza NHS pe disk temp
        tmp_nhs = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp_nhs.close()
        doc.save(tmp_nhs.name)
        doc.close()

        # Editeaza British Gas PDF - inlocuieste numele si adresa
        tmp_gas = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp_gas.close()
        _patch_british_gas(str(PDF_ANNEX), tmp_gas.name, data, font_path)

        # Combina NHS + British Gas editat
        merged = fitz.open()
        merged.insert_pdf(fitz.open(tmp_nhs.name))
        merged.insert_pdf(fitz.open(tmp_gas.name))
        pdf_bytes = merged.tobytes()
        merged.close()
        os.unlink(tmp_nhs.name)
        os.unlink(tmp_gas.name)
        print(f"[ANNEX] Merge OK - 4 pagini, nume/adresa actualizate")
    else:
        pdf_bytes = doc.tobytes()
        doc.close()
        print(f"[ANNEX] {PDF_ANNEX.name} lipsa - doar NHS 2 pagini")

    return pdf_bytes


def find_gps_overpass(city: str) -> list:
    import urllib.request, urllib.parse, json as _json

    query = f"""
[out:json][timeout:30];
area["name"="{city}"]["boundary"="administrative"]->.a;
(
  node["amenity"="doctors"](area.a);
  way["amenity"="doctors"](area.a);
);
out body 15;
"""
    data_out = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                  data=data_out,
                                  headers={"User-Agent": "NHSGPTool/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = _json.loads(r.read())
    elements = raw.get("elements", [])

    if not elements:
        geo_url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(city+', UK')}&format=json&limit=1"
        geo_req = urllib.request.Request(geo_url, headers={"User-Agent": "NHSGPTool/1.0"})
        with urllib.request.urlopen(geo_req, timeout=15) as r:
            geo = _json.loads(r.read())
        if geo:
            lat, lon = geo[0]["lat"], geo[0]["lon"]
            query2 = f"""
[out:json][timeout:30];
(
  node["amenity"="doctors"](around:8000,{lat},{lon});
  way["amenity"="doctors"](around:8000,{lat},{lon});
);
out body 15;
"""
            data2 = urllib.parse.urlencode({"data": query2}).encode()
            req2 = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                           data=data2,
                                           headers={"User-Agent": "NHSGPTool/1.0"})
            with urllib.request.urlopen(req2, timeout=30) as r:
                elements = _json.loads(r.read()).get("elements", [])

    results = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "").strip()
        if not name:
            continue
        house = tags.get("addr:housenumber", "")
        street = tags.get("addr:street", "")
        full_street = (house + " " + street).strip()
        town = tags.get("addr:city", tags.get("addr:town", tags.get("addr:suburb", city)))
        postcode = tags.get("addr:postcode", "")
        phone = tags.get("phone", tags.get("contact:phone", ""))
        results.append({"name": name, "street": full_street, "town": town,
                         "postcode": postcode, "phone": phone})
        if len(results) >= 10:
            break
    return results


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): return

    def _send(self, code, body, ct, dl=None):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("X-NHS-Tool-Version", VERSION)
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
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/find-gp":
            qs = parse_qs(parsed.query)
            city = (qs.get("city", [""])[0] or "").strip()
            if not city:
                self._send(400, b"Missing city", "text/plain"); return
            try:
                gps = find_gps_overpass(city)
                body = json.dumps(gps, ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, str(e).encode(), "text/plain")
            return
        if path in ("", "/"):
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
        if fp.suffix == ".html":
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
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
        if path != "/generate":
            self._send(404, b"Not found", "text/plain"); return
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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    if not PDF_SOURCE.is_file():
        print(f"EROARE: Nu gasesc {PDF_SOURCE}")
        input("Apasa Enter..."); sys.exit(1)
    server = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    font = _get_bold_font()
    print("=" * 55)
    print(f"  NHS GP Letter Tool v{VERSION}")
    print(f"  Font: {font}")
    print(f"  Deschide: {url}")
    print("=" * 55)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOprit.")


if __name__ == "__main__":
    main()
