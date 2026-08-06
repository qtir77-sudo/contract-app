#!/usr/bin/env python3
"""Social Service Care Letter Tool v1.0 - genereaza scrisoarea de confirmare
a circumstantelor familiale (Universal Credit Claim), pornind de la template-ul
Social_Service_Care.pdf. Foloseste cautare dinamica de text (ancore), nu
coordonate fixe ghicite - la fel ca celelalte scripturi din proiect."""
from __future__ import annotations
import json, sys, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
import fitz

DIR        = Path(__file__).resolve().parent
PDF_SOURCE = DIR / "Social_Service_Care.pdf"
VERSION    = "1.0"

BOLD_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    str(DIR / "arimo_bold.ttf"),
]
REGULAR_FONTS = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/ARIAL.TTF",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# Textele-ancora din template (placeholder-ele originale din Social_Service_Care.pdf)
ANCHOR_CARER_NAME   = "Mr Daniel-Stefan Tudor"
ANCHOR_CARER_DOB    = "17 July 1992"
ANCHOR_ADDRESS_LINE = "14 Jackson Road, MATLOCK, DE4 3JQ."
ANCHOR_DATE_LABEL   = "Date:"
ANCHOR_WORKER_NAME  = "Sarah Williams"
ANCHOR_DOB_MARK     = "Date of Birth:"  # apare pe fiecare linie de copil


def _font(bold: bool) -> str:
    paths = BOLD_FONTS if bold else REGULAR_FONTS
    for f in paths:
        if os.path.exists(f):
            return f
    return None  # cade pe helv/hebo built-in daca nu gasim niciun fisier


def _ins(page, x, y, text, size, bold=False, color=(0, 0, 0)):
    fp = _font(bold)
    if fp:
        page.insert_text((x, y), text, fontfile=fp, fontsize=size, color=color)
    else:
        page.insert_text((x, y), text, fontname=("hebo" if bold else "helv"), fontsize=size, color=color)


def _all_lines(page):
    """Intoarce toate liniile de pe pagina, ca lista de (text_concatenat, list_of_spans)."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"])
            out.append((text, line["spans"]))
    return out


def _replace_span_prefix(page, lines, anchor, new_value, bold=None):
    """Gaseste PRIMUL span al carui text incepe cu `anchor`, redacteaza-l si rescrie
    `new_value` + orice sufix ramas dupa ancora in span-ul original (ex: virgula lipita).
    Returneaza True daca a gasit si inlocuit."""
    for text, spans in lines:
        for s in spans:
            if s["text"].strip().startswith(anchor) or anchor in s["text"]:
                idx = s["text"].find(anchor)
                if idx == -1:
                    continue
                suffix = s["text"][idx + len(anchor):]
                x0, y0, x1, y1 = s["bbox"]
                size = s.get("size", 10)
                is_bold = bold if bold is not None else bool(s.get("flags", 0) & 16)
                page.add_redact_annot(fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1), fill=(1, 1, 1))
                page.apply_redactions()
                baseline_y = y1 - (y1 - y0) * 0.22
                _ins(page, x0, baseline_y, new_value + suffix, size, bold=is_bold)
                return True
    return False


def _replace_whole_line(page, lines, anchor, new_text, bold=None):
    """Gaseste linia care CONTINE `anchor` in text si o inlocuieste in intregime
    (util cand toata linia e un singur bloc de continut, ex: adresa)."""
    for text, spans in lines:
        if anchor in text:
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            size = spans[0].get("size", 10)
            is_bold = bold if bold is not None else bool(spans[0].get("flags", 0) & 16)
            page.add_redact_annot(fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1), fill=(1, 1, 1))
            page.apply_redactions()
            baseline_y = y1 - (y1 - y0) * 0.22
            _ins(page, x0, baseline_y, new_text, size, bold=is_bold)
            return True
    return False


def fill_social_letter(data: dict) -> bytes:
    if not PDF_SOURCE.is_file():
        raise FileNotFoundError(f"Nu gasesc PDF-ul sursa: {PDF_SOURCE}")

    doc = fitz.open(PDF_SOURCE)
    pg = doc[0]

    carer_name  = (data.get("carer_name") or "").strip()
    carer_dob   = (data.get("carer_dob") or "").strip()
    address     = (data.get("address") or "").strip()
    letter_date = (data.get("letter_date") or "").strip()
    worker_name = (data.get("worker_name") or "").strip()
    children    = data.get("children") or []  # [{"name":..., "dob":...}, ...]

    # ── 1. Numele tutorelui (apare de 2 ori: in prima fraza si la "reside with") ──
    if carer_name:
        lines = _all_lines(pg)
        ok1 = _replace_span_prefix(pg, lines, ANCHOR_CARER_NAME, carer_name, bold=True)
        lines = _all_lines(pg)  # re-scanam dupa fiecare redactare (textul s-a schimbat)
        ok2 = _replace_span_prefix(pg, lines, ANCHOR_CARER_NAME, carer_name, bold=True)
        print(f"[SOCIAL] Nume tutore inlocuit: aparitia1={ok1} aparitia2={ok2}")

    # ── 2. Data nasterii tutorelui ──────────────────────────────────────────────
    if carer_dob:
        lines = _all_lines(pg)
        ok = _replace_span_prefix(pg, lines, ANCHOR_CARER_DOB, carer_dob, bold=True)
        print(f"[SOCIAL] Data nastere tutore inlocuita: {ok}")

    # ── 3. Lista copiilor - suporta numar variabil (nu doar cele 4 din template) ─
    lines = _all_lines(pg)
    child_line_spans = []
    for text, spans in lines:
        if ANCHOR_DOB_MARK in text:
            x0 = min(s["bbox"][0] for s in spans)
            y0 = min(s["bbox"][1] for s in spans)
            x1 = max(s["bbox"][2] for s in spans)
            y1 = max(s["bbox"][3] for s in spans)
            size = spans[0].get("size", 10)
            child_line_spans.append((y0, y1, x0, x1, size))
    child_line_spans.sort(key=lambda t: t[0])

    # gaseste si bullet-urile "•" (span separat, la stanga liniei) ca sa stim x-ul lor
    bullet_x0 = None
    for text, spans in lines:
        if text.strip() == "•":
            bullet_x0 = spans[0]["bbox"][0]
            break

    if child_line_spans:
        orig_top = child_line_spans[0][0]
        orig_size = child_line_spans[0][4]
        name_x0 = child_line_spans[0][2]
        orig_spacing = (
            (child_line_spans[-1][0] - child_line_spans[0][0]) / (len(child_line_spans) - 1)
            if len(child_line_spans) > 1 else 17.3
        )
        # limita de jos disponibila = inceputul paragrafului urmator ("The above-named...")
        next_para_top = None
        for text, spans in lines:
            if "above-named children reside" in text:
                next_para_top = min(s["bbox"][1] for s in spans)
                break
        bottom_limit = (next_para_top - 12) if next_para_top else (orig_top + orig_spacing * (len(child_line_spans) + 2))

        n = len(children)
        if n > 0:
            usable_height = bottom_limit - orig_top
            if n <= len(child_line_spans):
                spacing = orig_spacing
                font_size = orig_size
            else:
                spacing = usable_height / max(n - 1, 1)
                font_size = orig_size if spacing >= 12 else max(7.0, orig_size * (spacing / orig_spacing))
                spacing = max(spacing, 9.0)

            # Sterge TOATE liniile vechi ale copiilor dintr-un singur bloc (de la prima la
            # ultima), ca sa nu ramana resturi cand numarul de copii se schimba
            block_x0 = (bullet_x0 - 2) if bullet_x0 is not None else (name_x0 - 10)
            block_y0 = child_line_spans[0][0] - 3
            block_y1 = max(child_line_spans[-1][1], orig_top + spacing * (n - 1) + orig_size + 4) + 3
            pg.add_redact_annot(fitz.Rect(block_x0, block_y0, 560, block_y1), fill=(1, 1, 1))
            pg.apply_redactions()

            for i, child in enumerate(children):
                cname = (child.get("name") or "").strip()
                cdob = (child.get("dob") or "").strip()
                if not cname:
                    continue
                y_top = orig_top + spacing * i
                y1_approx = y_top + font_size * 1.15
                baseline_y = y1_approx - (y1_approx - y_top) * 0.22
                if bullet_x0 is not None:
                    _ins(pg, bullet_x0, baseline_y, "\u2022", font_size, bold=False)
                line_text = f"{cname} \u2013 Date of Birth: {cdob}" if cdob else cname
                _ins(pg, name_x0, baseline_y, line_text, font_size, bold=True)
        else:
            # niciun copil - doar stergem liniile placeholder
            block_x0 = (bullet_x0 - 2) if bullet_x0 is not None else (name_x0 - 10)
            block_y0 = child_line_spans[0][0] - 3
            block_y1 = child_line_spans[-1][1] + 3
            pg.add_redact_annot(fitz.Rect(block_x0, block_y0, 560, block_y1), fill=(1, 1, 1))
            pg.apply_redactions()

    # ── 4. Adresa la care locuiesc copiii ("resides at ... address:") ──────────
    if address:
        lines = _all_lines(pg)
        ok = _replace_whole_line(pg, lines, ANCHOR_ADDRESS_LINE, address, bold=True)
        print(f"[SOCIAL] Adresa inlocuita: {ok}")

    # ── 5. Data scrisorii (colt sus-dreapta) ────────────────────────────────────
    if letter_date:
        lines = _all_lines(pg)
        found_date = False
        for text, spans in lines:
            if text.strip().startswith(ANCHOR_DATE_LABEL) and len(spans) >= 1:
                x0 = min(s["bbox"][0] for s in spans)
                y0 = min(s["bbox"][1] for s in spans)
                x1 = max(s["bbox"][2] for s in spans)
                y1 = max(s["bbox"][3] for s in spans)
                size = spans[0].get("size", 10)
                pg.add_redact_annot(fitz.Rect(x0 - 1, y0 - 1, x1 + 1, y1 + 1), fill=(1, 1, 1))
                pg.apply_redactions()
                baseline_y = y1 - (y1 - y0) * 0.22
                _ins(pg, x0, baseline_y, f"Date: {letter_date}", size, bold=False)
                found_date = True
                break
        print(f"[SOCIAL] Data scrisorii inlocuita: {found_date}")

    # ── 6. Numele asistentului social (semnatura tiparita) ──────────────────────
    if worker_name:
        lines = _all_lines(pg)
        ok = _replace_whole_line(pg, lines, ANCHOR_WORKER_NAME, worker_name, bold=True)
        print(f"[SOCIAL] Nume asistent social inlocuit: {ok}")

    pdf_bytes = doc.tobytes()
    doc.close()
    print(f"[SOCIAL] OK | carer='{carer_name}' | copii={len(children)} | adresa='{address}'")
    return pdf_bytes


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): return

    def _send(self, code, body, ct, dl=None):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("X-Social-Tool-Version", VERSION)
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
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        if path != "/generate-social":
            self._send(404, b"Not found", "text/plain"); return
        try:
            data = json.loads(raw.decode())
        except Exception:
            self._send(400, b"JSON invalid", "text/plain"); return
        try:
            pdf = fill_social_letter(data)
        except FileNotFoundError as e:
            self._send(404, str(e).encode(), "text/plain"); return
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send(500, f"Eroare: {e}".encode(), "text/plain"); return
        self._send(200, pdf, "application/pdf", "social-service-letter.pdf")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    if not PDF_SOURCE.is_file():
        print(f"EROARE: Nu gasesc {PDF_SOURCE}")
        sys.exit(1)
    server = HTTPServer(("127.0.0.1", port), Handler)
    print("=" * 55)
    print(f"  Social Service Letter Tool v{VERSION}")
    print(f"  Asculta pe portul {port}, ruta /generate-social")
    print("=" * 55)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOprit.")


if __name__ == "__main__":
    main()
