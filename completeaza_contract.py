#!/usr/bin/env python3
"""Contract tool v5.7 - Railway hosted version"""
from __future__ import annotations
import json, sys, io, re, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
import fitz
import anthropic

DIR         = Path(__file__).resolve().parent
PDF_SOURCE  = DIR / "test_contract_saca.pdf"
RECEIPT_PDF      = DIR / "adaugare_ppayscript.pdf"
BRITISH_GAS_PDF  = DIR / "british_gas_statement.pdf"
NI_LETTER_PDF    = DIR / "ni_letter.pdf"
ELECTRICITY_BILL_PDF = DIR / "electricity_bill.pdf"
VERSION          = "5.7"


# ── Culori branduri agenti UK ─────────────────────────────────────────────────
AGENT_COLORS = {
    "purplebricks": ("#6B2F93","#FFFFFF"),
    "savills":      ("#003057","#C4A14A"),
    "knight frank": ("#1B1B1B","#C9A84C"),
    "hamptons":     ("#1D3A5F","#FFFFFF"),
    "foxtons":      ("#E30613","#FFFFFF"),
    "connells":     ("#003087","#FFFFFF"),
    "your move":    ("#0072BC","#FFFFFF"),
    "reeds rains":  ("#E4002B","#FFFFFF"),
    "haart":        ("#E4002B","#FFFFFF"),
    "allen":        ("#003087","#FFFFFF"),
    "chancellors":  ("#1B3A6B","#FFFFFF"),
    "hunters":      ("#004225","#FFD700"),
    "martin":       ("#C8102E","#FFFFFF"),
    "peter alan":   ("#003087","#FFFFFF"),
    "john francis": ("#1B4332","#FFFFFF"),
    "howkins":      ("#1B2B5A","#C9A84C"),
    "romans":       ("#C8102E","#FFFFFF"),
    "winkworth":    ("#003087","#FFFFFF"),
    "fine":         ("#4A4A4A","#C9A84C"),
    "belvoir":      ("#003087","#FFFFFF"),
    "leaders":      ("#E30613","#FFFFFF"),
    "northwood":    ("#005596","#FFFFFF"),
    "chestertons":  ("#1B3A6B","#FFFFFF"),
    "strutt":       ("#1B2B5A","#FFFFFF"),
    "carter jonas": ("#1B3A6B","#C9A84C"),
    "jackson":      ("#003087","#FFFFFF"),
    "yopa":         ("#6B2F93","#FFFFFF"),
    "darlows":      ("#003087","#FFFFFF"),
    "bairstow":     ("#003087","#FFFFFF"),
    "whitegates":   ("#003087","#FFFFFF"),
    "bridgfords":   ("#C8102E","#FFFFFF"),
    "mann":         ("#C8102E","#FFFFFF"),
    "acorn":        ("#2E7D32","#FFFFFF"),
    "ewemove":      ("#7CB342","#FFFFFF"),
    "jll":          ("#E30613","#FFFFFF"),
    "barnard":      ("#1B2B5A","#FFFFFF"),
    "dafydd":       ("#1B4332","#FFFFFF"),
    "moginie":      ("#1B4332","#FFFFFF"),
    "stags":        ("#2E7D32","#FFFFFF"),
}

def _get_agent_colors(name: str):
    n = name.lower()
    for k, v in AGENT_COLORS.items():
        if k in n:
            return v
    return ("#1A5F4A","#FFFFFF")

def _make_logo_jpeg(display_name: str) -> bytes:
    """Genereaza JPEG 420x200 cu numele agentului si culorile brandului."""
    from PIL import Image as _PIL, ImageDraw as _Draw, ImageFont as _Font
    bg, fg = _get_agent_colors(display_name)
    img  = _PIL.new("RGB", (420,200), color=bg)
    draw = _Draw.Draw(img)
    font_size = 52
    font = None
    for fp in [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        try: font = _Font.truetype(fp, font_size); break
        except: pass
    words = display_name.split()
    if len(display_name) <= 14:
        lines = [display_name]
    elif len(words) == 2:
        lines = words
    else:
        mid = len(words)//2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    total_h = len(lines)*(font_size+8)
    y0 = (200-total_h)//2
    for i, line in enumerate(lines):
        bb = draw.textbbox((0,0), line, font=font)
        draw.text(((420-(bb[2]-bb[0]))//2, y0+i*(font_size+8)), line, fill=fg, font=font)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()

def _replace_logo_in_pdf(pdf_bytes: bytes, agent_display_name: str, logo_jpeg: bytes | None = None, page_index: int = -1) -> bytes:
    """Inlocuieste imaginea logo dintr-o pagina a PDF-ului cu logo-ul agentului.
    page_index: -1 = ultima pagina (comportament vechi). Pentru o pagina anume,
    foloseste indexul 0-based (ex: pagina 13 -> page_index=12)."""
    import pikepdf as _pk
    if logo_jpeg is None:
        logo_jpeg = _make_logo_jpeg(agent_display_name)
    print(f"[LOGO] Inlocuiesc logo (pagina index {page_index}) pentru '{agent_display_name}': {len(logo_jpeg)} bytes")
    pk = _pk.open(io.BytesIO(pdf_bytes))
    page = pk.pages[page_index]
    xobj = page["/Resources"]["/XObject"]
    keys = list(xobj.keys())
    print(f"[LOGO] XObjects in pagina index {page_index}: {keys}")
    target = None
    for k in keys:
        try:
            if str(xobj[k].get("/Subtype","")) == "/Image":
                target = k; break
        except: pass
    if target is None:
        target = "/FXX3"
    nxo = _pk.Stream(pk, logo_jpeg)
    nxo["/Type"]             = _pk.Name("/XObject")
    nxo["/Subtype"]          = _pk.Name("/Image")
    nxo["/Width"]            = 420
    nxo["/Height"]           = 200
    nxo["/ColorSpace"]       = _pk.Name("/DeviceRGB")
    nxo["/BitsPerComponent"] = 8
    nxo["/Filter"]           = _pk.Name("/DCTDecode")
    xobj[target] = nxo
    out = io.BytesIO(); pk.save(out); pk.close()
    result = out.getvalue()
    print(f"[LOGO] ✅ Logo inlocuit! PDF: {len(pdf_bytes)}b -> {len(result)}b")
    return result

# ── Agent name detection ───────────────────────────────────────────────────────
def _detect_agent_name(data: dict) -> str:
    """Extrage numele agentului din datele formularului."""
    # Prioritate: landlord_address (ex: "Purplebricks Cardiff, 1 Central Square...")
    addr = (data.get("landlord_address") or "").strip()
    if addr:
        first = addr.split(",")[0].strip()
        if first:
            return first
    return (data.get("landlord_name") or "Agent").strip()

def _get_logo_jpeg(data: dict) -> bytes:
    """Obtine logo JPEG: din b64 trimis de browser, sau genereaza automat."""
    import base64 as _b64
    # 1. Din browser (daca versiunea noua de HTML e incarcata)
    b64 = (data.get("agent_logo_b64") or "").strip()
    if b64 and len(b64) > 100:
        try:
            raw = b64.split(",",1)[1] if "," in b64 else b64
            logo_bytes = _b64.b64decode(raw)
            print(f"[LOGO] B64 din browser: {len(logo_bytes)} bytes")
            # Daca e SVG, convertim
            if logo_bytes.lstrip().startswith(b"<svg") or b"<svg" in logo_bytes[:200]:
                fills = re.findall(r'fill="(#[0-9A-Fa-f]{6})"', logo_bytes.decode())
                texts = re.findall(r'<text[^>]*>([^<]+)</text>', logo_bytes.decode())
                bg = fills[0] if fills else "#003087"
                fg = fills[1] if len(fills)>1 else "#FFFFFF"
                txt = " ".join(texts) if texts else "Agent"
                return _make_logo_jpeg_from_colors(txt, bg, fg)
            else:
                from PIL import Image as _PIL
                pil = _PIL.open(io.BytesIO(logo_bytes)).convert("RGB").resize((420,200), _PIL.LANCZOS)
                buf = io.BytesIO(); pil.save(buf,"JPEG",quality=95)
                return buf.getvalue()
        except Exception as e:
            print(f"[LOGO] Eroare b64: {e}")
    # 2. Automat din numele agentului
    agent = _detect_agent_name(data)
    print(f"[LOGO] Auto-generez din '{agent}'")
    return _make_logo_jpeg(agent)

def _make_logo_jpeg_from_colors(txt: str, bg: str, fg: str) -> bytes:
    from PIL import Image as _PIL, ImageDraw as _Draw, ImageFont as _Font
    img = _PIL.new("RGB",(420,200),color=bg)
    draw = _Draw.Draw(img)
    font = None
    for fp in ["C:/Windows/Fonts/arialbd.ttf","C:/Windows/Fonts/arial.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try: font = _Font.truetype(fp,52); break
        except: pass
    words = txt.split()
    lines = [txt] if len(txt)<=14 else (words if len(words)==2 else [" ".join(words[:len(words)//2])," ".join(words[len(words)//2:])])
    total_h = len(lines)*60
    y0 = (200-total_h)//2
    for i,line in enumerate(lines):
        bb = draw.textbbox((0,0),line,font=font)
        draw.text(((420-(bb[2]-bb[0]))//2,y0+i*60),line,fill=fg,font=font)
    buf = io.BytesIO(); img.save(buf,"JPEG",quality=95)
    return buf.getvalue()

# ── PDF fields ────────────────────────────────────────────────────────────────
FONT = "helv"; FONT_SIZE = 12; LABEL_GAP = 3.5; PAGE11_VALUE_X = 200.8
FIELDS: dict[str, dict] = {
    "landlord_name":    {"page":1,"label":"Name(s) of Landlord(s):","y_max":250},
    "landlord_address": {"page":1,"label":"Address of Landlord(s):","y_max":250},
    "landlord_phone":   {"page":1,"label":"Telephone:","y_max":200},
    "landlord_email":   {"page":1,"label":"Email:","y_max":200},
    "tenant_name":      {"page":1,"label":"Name(s) of Tenant(s):","y_min":250},
    "tenant_address":   {"page":1,"label":"Address of Tenant(s)","y_min":250,"gap":0},
    "tenant_phone":     {"page":1,"label":"Telephone:","y_min":300},
    "tenant_email":     {"page":1,"label":"Email:","y_min":300},
    "premises_address": {"page":1,"label":":","y_min":420,"y_max":425},
    "rent_amount":      {"page":1,"replace":"900.00"},
    "commencement_date":{"page":1,"replace":"04/04/2026"},
    "expiry_date":      {"page":1,"replace":"04/04/2027"},
    "leaflet_version":  {"page":9,"label":"version ","y_min":70,"y_max":85},
    "gas_cert_date":    {"page":9,"label":"dated","y_min":100,"y_max":110},
    "epc_date":         {"page":9,"label":"dated ","y_min":128,"y_max":138},
    "dob":              {"page":10,"label":"Date of Birth","fixed_x":PAGE11_VALUE_X},
    "ni_number":        {"page":10,"label":"National Insurance Nos","fixed_x":PAGE11_VALUE_X},
    "nationality":      {"page":10,"label":"Nationality","fixed_x":PAGE11_VALUE_X},
    "occupation":       {"page":10,"label":"Occupation","fixed_x":PAGE11_VALUE_X},
    "emergency_name":   {"page":10,"label":"Name","y_min":355,"y_max":370,"fixed_x":PAGE11_VALUE_X},
    "emergency_relationship":{"page":10,"label":"Relationship to you","fixed_x":PAGE11_VALUE_X},
    "emergency_address":{"page":10,"label":"Address","y_min":435,"y_max":450,"fixed_x":PAGE11_VALUE_X},
    "emergency_phone":  {"page":10,"label":"Telephone","y_min":478,"y_max":492,"fixed_x":PAGE11_VALUE_X},
    "emergency_email":  {"page":10,"label":"Email","y_min":520,"y_max":535,"fixed_x":PAGE11_VALUE_X},
    "tenant_print":     {"page":11,"point":(276.0,104.9)},
    "landlord_print":   {"page":11,"point":(277.0,238.5)},
    "tenant_date":      {"page":11,"point":(502.0,105.8)},
    "landlord_date":    {"page":11,"point":(505.0,237.6)},
}

def _find_span(page, needle, y_min=None, y_max=None):
    for block in page.get_text("dict")["blocks"]:
        if block.get("type")!=0: continue
        for line in block["lines"]:
            for span in line["spans"]:
                if needle not in span["text"]: continue
                t = span["bbox"][1]
                if y_min and t<y_min: continue
                if y_max and t>y_max: continue
                return span
    return None

def _bl(span):
    o=span.get("origin"); return o[1] if o else span["bbox"][1]+(span["bbox"][3]-span["bbox"][1])*0.78

def _insert(page, label, val, y_min=None, y_max=None, gap=LABEL_GAP, fx=None):
    s=_find_span(page,label,y_min,y_max)
    if not s: return
    page.insert_text((fx if fx else s["bbox"][2]+gap, _bl(s)), val, fontsize=s.get("size",FONT_SIZE), fontname=FONT, color=(0,0,0))

def _insert_pt(page, pt, val):
    page.insert_text((pt[0], pt[1]+FONT_SIZE*fitz.Font(FONT).ascender), val, fontsize=FONT_SIZE, fontname=FONT, color=(0,0,0))

def _replace_txt(page, contains, new_val):
    for block in page.get_text("dict")["blocks"]:
        if block.get("type")!=0: continue
        for line in block["lines"]:
            for span in line["spans"]:
                if contains not in span["text"]: continue
                page.add_redact_annot(fitz.Rect(span["bbox"])+(-1,-1,1,1), fill=(1,1,1))
                page.apply_redactions()
                page.insert_text((span["bbox"][0],_bl(span)), new_val, fontsize=span.get("size",FONT_SIZE), fontname=FONT, color=(0,0,0))
                return True
    return False

def _append_receipt(doc, data):
    if not RECEIPT_PDF.is_file(): raise FileNotFoundError(f"Nu gasesc: {RECEIPT_PDF}")
    rd = fitz.open(RECEIPT_PDF); doc.insert_pdf(rd); rd.close()
    p=doc[-1]; RF="helv"; RS=10
    def w(x,y,t): p.insert_text((x,y),t,fontsize=RS,fontname=RF,color=(0,0,0))
    def rw(r,x,y,t,s=None):
        p.add_redact_annot(fitz.Rect(r),fill=(1,1,1)); p.apply_redactions()
        p.insert_text((x,y),t,fontsize=s or RS,fontname=RF,color=(0,0,0))
    comm=(data.get("commencement_date") or "").strip()
    if comm:
        rw((77,122,200,138),77,133.33,f"Date: {comm}")
        try:
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            end=(datetime.strptime(comm,"%d/%m/%Y")+relativedelta(months=1)).strftime("%d/%m/%Y")
        except:
            pp=comm.split("/"); m=int(pp[1])+1; y=int(pp[2])
            if m>12: m=1;y+=1
            end=f"{pp[0]}/{m:02d}/{y}"
        rw((75,383,400,398),75,394.37,f"The Rent Covers the Period: from {comm} to {end}")
    tenant=(data.get("tenant_name") or "").strip()
    if tenant: w(142,164.56,tenant)
    addr=(data.get("premises_address") or "").strip()
    if addr: p.insert_text((210,189.50),addr,fontsize=9,fontname=RF,color=(0,0,0))
    rent=(data.get("rent_amount") or "").strip()
    if rent: w(145,235,rent); w(141,348.5,rent)
    phone=(data.get("landlord_phone") or "").strip()
    if phone: w(133,542,phone)
    parts=[]
    ln=(data.get("landlord_name") or "").strip()
    if ln: parts.append(ln)
    la=(data.get("landlord_address") or "").strip()
    if la: parts.extend([x.strip() for x in la.split(",") if x.strip()])
    for i,pt in enumerate(parts[:5]):
        p.insert_text((76,[455,470,484,499,513][i]),pt,fontsize=9,fontname=RF,color=(0,0,0))

_UK_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d[A-Z0-9]?\s*\d[A-Z]{2}$", re.IGNORECASE)


def _split_uk_address(addr: str) -> list[str]:
    """Imparte o adresa UK in maxim 3 randuri, in formatul standard folosit pe facturi:
    randul 1 = numar + strada, randul 2 = oras, randul 3 = cod postal.

    Adresele introduse cu virgula dupa numarul casei (ex: "162, Shirley Road, Birmingham, B27 XXX")
    ar da 4+ bucati daca am desparti simplu dupa virgula - de aceea recunoastem codul postal
    (ultima bucata) si orasul (penultima), si lipim tot restul (numar + strada) pe un singur rand,
    ca sa nu se piarda nimic si sa incapa exact in cele 3 randuri disponibile in template.
    """
    if "," in addr:
        parts = [p.strip() for p in addr.split(",") if p.strip()]
    elif "\n" in addr:
        parts = [p.strip() for p in addr.split("\n") if p.strip()]
    else:
        return [addr]

    if len(parts) <= 1:
        return parts

    if len(parts) <= 3:
        return parts

    # Mai mult de 3 bucati: comprimam in exact 3 randuri.
    if _UK_POSTCODE_RE.match(parts[-1]):
        postcode = parts[-1]
        rest = parts[:-1]
        if len(rest) >= 2:
            city = rest[-1]
            street = " ".join(rest[:-1])
            return [street, city, postcode]
        return [rest[0] if rest else "", postcode]

    # Nu am recunoscut un cod postal clar la final - lipim tot ce e in plus pe primul rand,
    # pastram ultimele 2 bucati (probabil oras + cod postal) separate.
    street = " ".join(parts[:-2])
    return [street, parts[-2], parts[-1]]


def _append_british_gas(doc, data):
    """Adauga British Gas statement PDF la finalul documentului si inlocuieste datele chiriasului."""
    if not BRITISH_GAS_PDF.is_file():
        print(f"[BRITISH GAS] Nu gasesc: {BRITISH_GAS_PDF}, skip.")
        return
    bg_doc = fitz.open(BRITISH_GAS_PDF)
    bg_page_count = bg_doc.page_count
    doc.insert_pdf(bg_doc)
    bg_doc.close()
    pg = doc[-bg_page_count]

    RS = 12.0  # ArialMT 12pt - identic cu originalul

    # Cauta Arial - primul disponibil (Windows are arial.ttf, Linux are Liberation)
    arial_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/ARIAL.TTF",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    fontfile = None
    for fp in arial_paths:
        if Path(fp).is_file():
            fontfile = fp
            break

    def ins(x, y, text):
        if fontfile:
            pg.insert_text((x, y), text, fontsize=RS, fontfile=fontfile, color=(0, 0, 0))
        else:
            pg.insert_text((x, y), text, fontsize=RS, fontname="helv", color=(0, 0, 0))

    tenant = (data.get("tenant_name") or "").strip()
    addr   = (data.get("premises_address") or data.get("tenant_address") or "").strip()

    # Sterge tot blocul nume+adresa dintr-o singura redactare
    pg.add_redact_annot(fitz.Rect(52.85, 136.40, 320, 195.92), fill=(1, 1, 1))
    pg.apply_redactions()

    # Scrie numele - origin exact din original: x=52.852, y=147.264
    if tenant:
        ins(52.852, 147.264, tenant)

    # Scrie adresa - origini exacte: y=162.639, 178.014, 193.389 (spacing 15.375pt)
    if addr:
        parts = _split_uk_address(addr)
        y_origins = [162.639, 178.014, 193.389, 208.764]
        for i, part in enumerate(parts[:4]):
            ins(52.852, y_origins[i], part)

    # Calculeaza automat "Covering: <data> to <data + 1 luna>" pe baza commencement_date
    # (aceeasi data folosita la "Date:" din Rent Receipt)
    comm = (data.get("commencement_date") or "").strip()
    if comm:
        try:
            from datetime import datetime
            from dateutil.relativedelta import relativedelta
            start_dt = datetime.strptime(comm, "%d/%m/%Y")
            end_dt = start_dt + relativedelta(months=1)
            start_str = start_dt.strftime("%d %B %Y")
            end_str = end_dt.strftime("%d %B %Y")
        except Exception as e:
            print(f"[BRITISH GAS] EROARE parsare commencement_date '{comm}': {e}")
            start_str = end_str = None

        if start_str and end_str:
            # Gaseste linia care contine "Covering:" pe pagina British Gas
            covering_spans = None
            for block in pg.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    line_text = "".join(s["text"] for s in line["spans"])
                    if "Covering" in line_text:
                        covering_spans = line["spans"]
                        break
                if covering_spans:
                    break

            if covering_spans:
                label_span = next((s for s in covering_spans if "Covering" in s["text"]), None)
                value_spans = [s for s in covering_spans if s is not label_span]
                if value_spans:
                    vx0 = min(s["bbox"][0] for s in value_spans)
                    vy0 = min(s["bbox"][1] for s in value_spans)
                    vx1 = max(s["bbox"][2] for s in value_spans)
                    vy1 = max(s["bbox"][3] for s in value_spans)
                    vsize = value_spans[0].get("size", 9)
                    pg.add_redact_annot(fitz.Rect(vx0 - 1, vy0 - 1, vx1 + 1, vy1 + 1), fill=(1, 1, 1))
                    pg.apply_redactions()
                    baseline_y = vy1 - (vy1 - vy0) * 0.22
                    pg.insert_text((vx0, baseline_y), f"{start_str} to {end_str}",
                                    fontsize=vsize, fontname="helv", color=(0, 0, 0))
                    print(f"[BRITISH GAS] Covering actualizat: {start_str} to {end_str}")
                else:
                    print("[BRITISH GAS] Covering: gasit label dar nu si valoarea de inlocuit")
            else:
                print("[BRITISH GAS] Nu am gasit linia 'Covering:' pe pagina statement-ului")

            # Gaseste linia "Statement date:" si o seteaza egal cu data de sfarsit a perioadei
            # (la fel ca in documentul original: Covering ... to 16 May 2026 => Statement date: 16 May 2026)
            statement_spans = None
            for block in pg.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    line_text = "".join(s["text"] for s in line["spans"])
                    if "Statement date" in line_text:
                        statement_spans = line["spans"]
                        break
                if statement_spans:
                    break

            if statement_spans:
                label_span = next((s for s in statement_spans if "Statement date" in s["text"]), None)
                value_spans = [s for s in statement_spans if s is not label_span]
                if value_spans:
                    vx0 = min(s["bbox"][0] for s in value_spans)
                    vy0 = min(s["bbox"][1] for s in value_spans)
                    vx1 = max(s["bbox"][2] for s in value_spans)
                    vy1 = max(s["bbox"][3] for s in value_spans)
                    vsize = value_spans[0].get("size", 9)
                    pg.add_redact_annot(fitz.Rect(vx0 - 1, vy0 - 1, vx1 + 1, vy1 + 1), fill=(1, 1, 1))
                    pg.apply_redactions()
                    baseline_y = vy1 - (vy1 - vy0) * 0.22
                    pg.insert_text((vx0, baseline_y), end_str,
                                    fontsize=vsize, fontname="helv", color=(0, 0, 0))
                    print(f"[BRITISH GAS] Statement date actualizat: {end_str}")
                else:
                    print("[BRITISH GAS] Statement date: gasit label dar nu si valoarea de inlocuit")
            else:
                print("[BRITISH GAS] Nu am gasit linia 'Statement date:' pe pagina statement-ului")

        # Actualizeaza automat "Your opening balance on <data>" si "Your new balance on <data>"
        # cu datele de start/sfarsit (start_str / end_str) calculate mai sus. Ambele texte sunt
        # scrise pe mai multe randuri (paragraf ingust, ex: "Your opening" / "balance on 01" /
        # "March 2026"), deci gasim exact liniile cu ziua si cu luna+anul si le inlocuim pastrand
        # fontul/culoarea originale (albastru, bold) - nu punem culoare neagra ca la celelalte campuri.
        def _span_color(span):
            c = span.get("color", 0)
            return ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)

        def _get_font_spec(page, span):
            """Foloseste DOAR Helvetica (built-in, sigur). Am incercat sa extragem fontul original
            embedded din PDF, dar fonturile din acest document sunt "subsetate" (contin doar
            literele/cifrele deja folosite in textul original) - la scriere de text NOU cu acel
            font apar patratele goale (glyph-uri lipsa), nu caracterele corecte. Helvetica ramane
            singura varianta sigura, care poate reda orice caracter."""
            flags = span.get("flags", 0)
            return ("hebo" if (flags & 16) else "helv"), None

        def _write_text(page, x, y, text, size, color, fontname, fontbuffer):
            """Scrie textul cu fontul custom daca exista buffer (inregistrandu-l chiar acum, la
            ultima secunda), cu fallback SIGUR pe Helvetica daca orice pas esueaza - generarea nu
            trebuie sa crape niciodata din cauza unui font."""
            active_font = fontname
            if fontbuffer:
                try:
                    page.insert_font(fontname=fontname, fontbuffer=fontbuffer)
                except Exception as e:
                    print(f"[BRITISH GAS] insert_font a esuat ('{e}'), revin la Helvetica")
                    active_font = "helv"
            try:
                page.insert_text((x, y), text, fontsize=size, fontname=active_font, color=color)
            except Exception as e:
                print(f"[BRITISH GAS] insert_text cu font custom a esuat ('{e}'), revin la Helvetica")
                page.insert_text((x, y), text, fontsize=size, fontname="helv", color=color)

        def _update_wrapped_balance_date(label, must_include, must_exclude, date_str):
            """Cauta blocul care contine toate cuvintele din must_include si niciunul din
            must_exclude (ex: 'opening'+'balance', exclude 'new' - ca sa nu confundam cele doua
            texte 'Your opening balance on ...' si 'Your new balance on ...'), apoi inlocuieste
            ziua si luna+anul pastrand pozitia/wrap-ul original."""
            if not date_str:
                return
            try:
                new_day, new_month, new_year = date_str.split(" ")
            except Exception:
                return

            target_lines = None
            for block in pg.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                block_text = " ".join("".join(s["text"] for s in ln["spans"]) for ln in block["lines"]).lower()
                if all(w in block_text for w in must_include) and not any(w in block_text for w in must_exclude):
                    target_lines = block["lines"]
                    break

            if not target_lines:
                print(f"[BRITISH GAS] Nu am gasit blocul 'Your {label} balance on'")
                return

            day_line = None
            month_line = None
            full_date_line = None
            for ln in target_lines:
                ltxt = "".join(s["text"] for s in ln["spans"]).strip()
                if re.fullmatch(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", ltxt):
                    # cazul "25 March 2026" - ziua+luna+anul pe acelasi rand
                    full_date_line = ln
                elif re.search(r"\bon\s+\d{1,2}\b\s*$", ltxt, re.IGNORECASE):
                    day_line = ln
                elif re.fullmatch(r"[A-Za-z]+\s+\d{4}", ltxt):
                    month_line = ln

            if full_date_line:
                f_span = full_date_line["spans"][0]
                fx0, fy0, fx1, fy1 = f_span["bbox"]
                fsize = f_span.get("size", 12)
                fcolor = _span_color(f_span)
                ffont, fbuf = _get_font_spec(pg, f_span)
                pg.add_redact_annot(fitz.Rect(fx0 - 1, fy0 - 1, fx1 + 1, fy1 + 1), fill=(1, 1, 1))
                pg.apply_redactions()
                baseline_y = fy1 - (fy1 - fy0) * 0.22
                _write_text(pg, fx0, baseline_y, f"{new_day} {new_month} {new_year}",
                            fsize, fcolor, ffont, fbuf)
                print(f"[BRITISH GAS] {label} balance - data actualizata: {new_day} {new_month} {new_year}")
                return

            if day_line:
                d_span = day_line["spans"][-1]
                dx0, dy0, dx1, dy1 = d_span["bbox"]
                dsize = d_span.get("size", 12)
                dcolor = _span_color(d_span)
                dfont, dbuf = _get_font_spec(pg, d_span)
                pg.add_redact_annot(fitz.Rect(dx0 - 1, dy0 - 1, dx1 + 1, dy1 + 1), fill=(1, 1, 1))
                pg.apply_redactions()
                new_day_line_text = re.sub(r"\d{1,2}\s*$", new_day, "".join(s["text"] for s in day_line["spans"]).strip())
                baseline_y = dy1 - (dy1 - dy0) * 0.22
                _write_text(pg, dx0, baseline_y, new_day_line_text, dsize, dcolor, dfont, dbuf)
                print(f"[BRITISH GAS] {label} balance - zi actualizata: {new_day_line_text}")
            else:
                print(f"[BRITISH GAS] Nu am gasit linia cu ziua pentru 'Your {label} balance on'")

            if month_line:
                m_span = month_line["spans"][0]
                mx0, my0, mx1, my1 = m_span["bbox"]
                msize = m_span.get("size", 12)
                mcolor = _span_color(m_span)
                mfont, mbuf = _get_font_spec(pg, m_span)
                pg.add_redact_annot(fitz.Rect(mx0 - 1, my0 - 1, mx1 + 1, my1 + 1), fill=(1, 1, 1))
                pg.apply_redactions()
                _write_text(pg, mx0, my1 - (my1 - my0) * 0.22, f"{new_month} {new_year}",
                            msize, mcolor, mfont, mbuf)
                print(f"[BRITISH GAS] {label} balance - luna/an actualizate: {new_month} {new_year}")
            else:
                print(f"[BRITISH GAS] Nu am gasit linia cu luna/anul pentru 'Your {label} balance on'")

        _update_wrapped_balance_date("opening", must_include=["opening", "balance"], must_exclude=["new"], date_str=start_str)
        _update_wrapped_balance_date("new", must_include=["new", "balance"], must_exclude=["opening"], date_str=end_str)

        # Pagina 2 a statement-ului ("Your account in detail") are acelasi tip de text dar
        # scris pe UN SINGUR rand si in negru (nu albastru, nu impartit pe mai multe randuri):
        # "Your opening balance on ..." si "Your new balance on ...". Le actualizam pe amandoua.
        def _update_single_line_date(page, anchor, date_str):
            if not date_str:
                return
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for ln in block["lines"]:
                    ltxt = "".join(s["text"] for s in ln["spans"])
                    if anchor in ltxt.lower() and re.search(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", ltxt):
                        lx0 = min(s["bbox"][0] for s in ln["spans"])
                        ly0 = min(s["bbox"][1] for s in ln["spans"])
                        lx1 = max(s["bbox"][2] for s in ln["spans"])
                        ly1 = max(s["bbox"][3] for s in ln["spans"])
                        lsize = ln["spans"][0].get("size", 11)
                        lcolor = _span_color(ln["spans"][0])
                        lfont, lbuf = _get_font_spec(page, ln["spans"][0])
                        new_line_text = re.sub(r"\d{1,2}\s+[A-Za-z]+\s+\d{4}", date_str, ltxt)
                        page.add_redact_annot(fitz.Rect(lx0 - 1, ly0 - 1, lx1 + 1, ly1 + 1), fill=(1, 1, 1))
                        page.apply_redactions()
                        baseline_y = ly1 - (ly1 - ly0) * 0.22
                        _write_text(page, lx0, baseline_y, new_line_text, lsize, lcolor, lfont, lbuf)
                        print(f"[BRITISH GAS] Pagina 2 - '{anchor}' actualizata: {new_line_text}")
                        return True
            print(f"[BRITISH GAS] Pagina 2 - nu am gasit '{anchor} ...'")
            return False

        if bg_page_count > 1:
            pg2 = doc[-bg_page_count + 1]
            _update_single_line_date(pg2, "opening balance", start_str)
            _update_single_line_date(pg2, "new balance", end_str)

            # "20 Apr 26- 20 May 26" si "20 Apr - 20 May 2026" - perioada de facturare, in doua
            # formate diferite (scurt: an pe 2 cifre la ambele date; lung: an pe 4 cifre doar la a
            # doua data). Ambele apar la INCEPUTUL randului lor (restul randului contine alte
            # detalii - kWh/pret sau "Total Gas costs"/suma). Cautam potrivirea EXACT la inceputul
            # textului liniei, indiferent in cate span-uri e impartita data (uneori 1, alteori mai
            # multe din cauza stilului), redactam doar span-urile afectate si le rescriem cu
            # fontul/culoarea span-ului original.
            if comm:
                def _replace_line_prefix_date(page, pattern, replacement):
                    rx = re.compile(pattern)
                    for block in page.get_text("dict")["blocks"]:
                        if block.get("type") != 0:
                            continue
                        for ln in block["lines"]:
                            spans = ln["spans"]
                            full_text = "".join(s["text"] for s in spans)
                            m = rx.match(full_text)  # match doar la INCEPUTUL liniei
                            if not m:
                                continue
                            end_pos = m.end()
                            affected = []
                            pos = 0
                            for s in spans:
                                s_start, s_end = pos, pos + len(s["text"])
                                if s_start < end_pos:
                                    affected.append(s)
                                pos = s_end
                                if pos >= end_pos:
                                    break
                            if not affected:
                                continue
                            ax0 = min(s["bbox"][0] for s in affected)
                            ay0 = min(s["bbox"][1] for s in affected)
                            ax1 = max(s["bbox"][2] for s in affected)
                            ay1 = max(s["bbox"][3] for s in affected)
                            asize = affected[0].get("size", 11)
                            acolor = _span_color(affected[0])
                            afont, abuf = _get_font_spec(page, affected[0])
                            page.add_redact_annot(fitz.Rect(ax0 - 1, ay0 - 1, ax1 + 1, ay1 + 1), fill=(1, 1, 1))
                            page.apply_redactions()
                            baseline_y = ay1 - (ay1 - ay0) * 0.22
                            _write_text(page, ax0, baseline_y, replacement, asize, acolor, afont, abuf)
                            print(f"[BRITISH GAS] Pagina 2 - perioada actualizata: {replacement}")
                            return True
                    return False

                short_range = f"{start_dt.strftime('%d %b %y')}- {end_dt.strftime('%d %b %y')}"
                full_range = f"{start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b %Y')}"

                ok1 = _replace_line_prefix_date(
                    pg2, r"\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\s*-\s*\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\b", short_range)
                if not ok1:
                    print("[BRITISH GAS] Pagina 2 - nu am gasit perioada scurta (ex: '20 Apr 26- 20 May 26')")

                ok2 = _replace_line_prefix_date(
                    pg2, r"\d{1,2}\s+[A-Za-z]{3}\s*-\s*\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b", full_range)
                if not ok2:
                    print("[BRITISH GAS] Pagina 2 - nu am gasit perioada lunga (ex: '20 Apr - 20 May 2026')")

    print(f"[BRITISH GAS] OK | font={'Arial' if fontfile else 'helv'} {RS}pt | '{tenant}'")


def _append_ni_letter(doc, data):
    """Adauga scrisoarea National Insurance (HMRC) la final si inlocuieste datele chiriasului."""
    # NI_LETTER_PDF already defined globally
    if not NI_LETTER_PDF.is_file():
        print(f"[NI LETTER] Nu gasesc: {NI_LETTER_PDF}, skip.")
        return
    ni_doc = fitz.open(NI_LETTER_PDF)
    ni_page_count = ni_doc.page_count
    doc.insert_pdf(ni_doc)
    ni_doc.close()
    pg = doc[-ni_page_count]

    RS = 12.0  # ArialMT 12pt - identic cu originalul

    arial_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/ARIAL.TTF",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    fontfile = None
    for fp in arial_paths:
        if Path(fp).is_file():
            fontfile = fp
            break

    def ins(x, y, text, size=RS):
        if fontfile:
            pg.insert_text((x, y), text, fontsize=size, fontfile=fontfile, color=(0, 0, 0))
        else:
            pg.insert_text((x, y), text, fontsize=size, fontname="helv", color=(0, 0, 0))

    tenant = (data.get("tenant_name") or "").strip()
    addr   = (data.get("premises_address") or data.get("tenant_address") or "").strip()

    # ── Sterge blocul nume + adresa (bbox: y=111.7 -> 167) ────────────────────
    pg.add_redact_annot(fitz.Rect(73, 107, 350, 170), fill=(1, 1, 1))
    # ── Sterge al doilea nume (bbox: y=204) ───────────────────────────────────
    pg.add_redact_annot(fitz.Rect(73, 199, 400, 220), fill=(1, 1, 1))
    pg.apply_redactions()

    # ── Scrie numele (origin exact: x=73, y=122.639) ──────────────────────────
    if tenant:
        ins(73.0, 122.639, tenant)

    # ── Scrie adresa (origin exact: y=135.889, 149.889, 163.889, spacing=14) ──
    if addr:
        parts = _split_uk_address(addr)
        y_origins = [135.889, 149.889, 163.889, 177.889]
        for i, part in enumerate(parts[:4]):
            ins(73.0, y_origins[i], part)

    # ── Scrie al doilea nume fara titlu (origin: x=73, y=214.889) ────────────
    # In noul template: "Chimezie Gerald Okeugbo" (fara Mr/Mrs, normal case)
    if tenant:
        # Scoate titlul (Mr/Mrs/Miss/Ms/Dr) daca exista
        name_no_title = re.sub(r'^(Mr|Mrs|Miss|Ms|Dr|Prof)\.?\s+', '', tenant, flags=re.IGNORECASE).strip()
        ins(73.0, 214.889, name_no_title)

    # ── Inlocuieste NI number (teal fill + Helvetica-Bold 21pt, centrat) ───────
    ni_number = (data.get("ni_number") or "").strip().upper()
    if ni_number:
        TEAL = (0.8554700016975403, 0.9570299983024597, 0.9492200016975403)
        ni_size = 21.0

        # Acopera textul vechi cu teal (pastreaza background)
        pg.draw_rect(fitz.Rect(70.86, 246.5, 524.40, 276.9),
                     color=TEAL, fill=TEAL, width=0)

        # Helvetica-Bold built-in (exact fontul din original)
        f_tmp = fitz.Font("hebo")
        tw = f_tmp.text_length(ni_number, fontsize=ni_size)
        box_cx = (70.86 + 524.40) / 2
        pg.insert_text((box_cx - tw / 2, 264.889), ni_number,
                       fontsize=ni_size, fontname="hebo", color=(0, 0, 0))

    print(f"[NI LETTER] OK | '{tenant}' | NI='{ni_number}'")


def _append_electricity_bill(doc, data):
    """Adauga factura de electricitate (British Gas Business) la finalul PDF-ului.
    Numele si adresa se cauta dinamic in text (ca la Covering/Statement date), nu pe coordonate fixe ghicite.
    IMPORTANT: liniile din acest template sunt foarte apropiate (~1.2pt), asa ca redactam TOATE
    liniile intr-un singur apply_redactions(), apoi scriem tot textul nou - altfel o redactare
    ulterioara "mananca" din textul deja scris pe linia de deasupra."""
    if not ELECTRICITY_BILL_PDF.is_file():
        print(f"[ELECTRICITY BILL] Nu gasesc: {ELECTRICITY_BILL_PDF}, skip.")
        return
    bill_doc = fitz.open(ELECTRICITY_BILL_PDF)
    bill_page_count = bill_doc.page_count
    doc.insert_pdf(bill_doc)
    bill_doc.close()
    pg = doc[-bill_page_count]

    tenant = (data.get("tenant_name") or "").strip()
    addr   = (data.get("premises_address") or data.get("tenant_address") or "").strip()

    def _line_bbox(page, anchor):
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                line_text = "".join(s["text"] for s in line["spans"])
                if anchor in line_text:
                    x0 = min(s["bbox"][0] for s in line["spans"])
                    y0 = min(s["bbox"][1] for s in line["spans"])
                    x1 = max(s["bbox"][2] for s in line["spans"])
                    y1 = max(s["bbox"][3] for s in line["spans"])
                    fs = line["spans"][0].get("size", 10)
                    return (x0, y0, x1, y1, fs)
        return None

    # PAS 1: gaseste TOATE liniile-tinta (pe textul original, neatins) inainte de orice redactare
    # Nume+adresa stau intr-un bloc separat (in coltul stang, randuri lipite) de "Bill date:"
    # (care e sus, in alt colt al paginii) -> le tinem in liste separate, ca sa nu le amestecam
    # intr-o singura redactare care ar acoperi gresit tot spatiul dintre ele.
    addr_targets = []   # [((x0,y0,x1,y1,fs), text_nou), ...] - nume + linii adresa
    bill_date_target = None  # ((x0,y0,x1,y1,fs), text_nou) sau None

    if tenant:
        b = _line_bbox(pg, "Nicolaie")
        if b:
            addr_targets.append((b, tenant))
        else:
            print("[ELECTRICITY BILL] Nu am gasit linia numelui (ancora 'Nicolaie')")

    if addr:
        parts = _split_uk_address(addr)
        anchors = ["Gregson", "LANCASTER", "LA1"]
        for i, anchor in enumerate(anchors):
            b = _line_bbox(pg, anchor)
            if not b:
                print(f"[ELECTRICITY BILL] Nu am gasit ancora '{anchor}'")
                continue
            # Daca adresa are mai putine linii decat template-ul, liniile ramase se golesc
            # (nu lasam textul vechi/gresit, ex: "LA1 3DH" ramas dintr-o adresa diferita)
            new_text = parts[i] if i < len(parts) else ""
            addr_targets.append((b, new_text))

    # "Bill date:" — calculat automat pe baza commencement_date (aceeasi data folosita si la Covering/Statement date)
    comm = (data.get("commencement_date") or "").strip()
    if comm:
        try:
            from datetime import datetime
            bill_dt = datetime.strptime(comm, "%d/%m/%Y")
            bill_date_str = bill_dt.strftime("%d %b %Y")
        except Exception as e:
            print(f"[ELECTRICITY BILL] Eroare parsare commencement_date '{comm}': {e}")
            bill_date_str = None

        if bill_date_str:
            found_line = None
            for block in pg.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    line_text = "".join(s["text"] for s in line["spans"])
                    if "Bill date" in line_text:
                        found_line = line["spans"]
                        break
                if found_line:
                    break

            if found_line:
                label_span = next((s for s in found_line if "Bill date" in s["text"]), None)
                value_spans = [s for s in found_line if s is not label_span]
                if value_spans:
                    vx0 = min(s["bbox"][0] for s in value_spans)
                    vy0 = min(s["bbox"][1] for s in value_spans)
                    vx1 = max(s["bbox"][2] for s in value_spans)
                    vy1 = max(s["bbox"][3] for s in value_spans)
                    vsize = value_spans[0].get("size", 9)
                    bill_date_target = ((vx0, vy0, vx1, vy1, vsize), bill_date_str)
                else:
                    print("[ELECTRICITY BILL] 'Bill date:' gasit dar fara valoare de inlocuit")
            else:
                print("[ELECTRICITY BILL] Nu am gasit linia 'Bill date:'")

    # PAS 2: redacteaza.
    # (a) Blocul nume+adresa (randuri lipite in coltul stang) se sterge dintr-un SINGUR dreptunghi
    #     generos care acopera tot blocul - la fel ca la British Gas - ca sa nu ramana resturi/glife
    #     izolate (ex: un caracter singuratic ramas intre randuri) nedetectate de anchore.
    # (b) "Bill date:" e o linie izolata, in alt colt al paginii -> redactare separata, fina.
    BLOCK_PAD_X = 4       # extra pe orizontala, ca sa acopere toata latimea blocului
    BLOCK_PAD_TOP = 2
    BLOCK_PAD_BOTTOM = 6  # extra generos jos, ca sa "inghita" orice rest intre bloc si textul urmator
    PAD = 0.3             # padding fin pentru Bill date (linie separata)

    if addr_targets:
        bx0 = min(t[0][0] for t in addr_targets) - BLOCK_PAD_X
        by0 = min(t[0][1] for t in addr_targets) - BLOCK_PAD_TOP
        bx1 = max(t[0][2] for t in addr_targets) + BLOCK_PAD_X
        by1 = max(t[0][3] for t in addr_targets) + BLOCK_PAD_BOTTOM
        pg.add_redact_annot(fitz.Rect(bx0, by0, bx1, by1), fill=(1, 1, 1))

    if bill_date_target:
        (x0, y0, x1, y1, fs), _ = bill_date_target
        pg.add_redact_annot(fitz.Rect(x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD), fill=(1, 1, 1))

    if addr_targets or bill_date_target:
        pg.apply_redactions()

    # PAS 3: abia acum scrie tot textul nou (dupa ce toate redactarile au fost deja aplicate)
    all_targets = list(addr_targets)
    if bill_date_target:
        all_targets.append(bill_date_target)

    for (x0, y0, x1, y1, fs), new_text in all_targets:
        if not new_text:
            continue
        baseline_y = y1 - (y1 - y0) * 0.22
        pg.insert_text((x0, baseline_y), new_text, fontsize=fs, fontname="helv", color=(0, 0, 0))

    print(f"[ELECTRICITY BILL] OK | '{tenant}' | pagini adaugate={bill_page_count} | linii inlocuite={len(all_targets)}")




def _make_white_jpeg() -> bytes:
    """Genereaza JPEG alb 420x200 pentru a sterge logo-ul."""
    from PIL import Image as _PIL
    img = _PIL.new("RGB", (420, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _widen_boxes_page2(doc):
    """Extinde chenarele - apelata DUPA save/reload, deci get_text vede tot textul."""
    pg = doc[1]
    pw = pg.rect.width
    new_x0 = 15.0
    new_x1 = pw - 15.0
    PADDING_BOTTOM = 14
    GAP_BETWEEN    = 8

    drawings = pg.get_drawings()
    boxes = []
    for d in drawings:
        r = d.get("rect")
        if r and r.width > 150 and r.height > 30 and r.x0 > 5:
            boxes.append(r)
    boxes.sort(key=lambda r: r.y0)
    unique = []
    for r in boxes:
        if not any(abs(r.y0 - u.y0) < 5 for u in unique):
            unique.append(r)
    main_boxes = unique[:3]

    if len(main_boxes) < 2:
        print(f"[BOXES] {len(main_boxes)} boxuri - skip")
        return

    all_spans = []
    for block in pg.get_text("dict")["blocks"]:
        if block.get("type") != 0: continue
        for line in block["lines"]:
            for span in line["spans"]:
                all_spans.append(span["bbox"])

    def content_bottom(box, is_last=False):
        extra = 80 if is_last else 2
        spans = [b for b in all_spans if b[1] >= box.y0 - 2 and b[3] <= box.y1 + extra]
        return (max(b[3] for b in spans) + PADDING_BOTTOM) if spans else box.y1

    new_rects = []
    for i, r in enumerate(main_boxes):
        y0 = r.y0 if i == 0 else new_rects[-1][3] + GAP_BETWEEN
        y1 = content_bottom(r, is_last=(i == len(main_boxes) - 1))
        y1 = max(y1, y0 + 40)
        new_rects.append((new_x0, y0, new_x1, y1))

    if main_boxes:
        pg.draw_rect(fitz.Rect(5, main_boxes[0].y0 - 3, pw - 5, main_boxes[-1].y1 + 3),
                     color=(1,1,1), fill=(1,1,1), width=0)
    for (bx0, by0, bx1, by1) in new_rects:
        pg.draw_rect(fitz.Rect(bx0, by0, bx1, by1), color=(0,0,0), fill=None, width=0.5)

    print(f"[BOXES] OK - ultimul chenar y1={new_rects[-1][3]:.1f}")


def _insert_payment_lines(doc, data, rent_y_info: dict):
    """Insereaza First payment (pe linia Expiry date) + Deposit (pe linia Rent), in dreapta."""
    import re as _re
    pg = doc[1]
    rent_amount = (data.get("rent_amount") or "").strip()
    comm_date   = (data.get("commencement_date") or "").strip()

    if not rent_amount:
        for block in pg.get_text("dict")["blocks"]:
            if block.get("type") != 0: continue
            for line in block["lines"]:
                for span in line["spans"]:
                    m = _re.search(r'Rent.*?([\d,]+\.\d{2})', span["text"])
                    if m: rent_amount = m.group(1).strip(); break
        if not rent_amount: rent_amount = "900.00"
    if not comm_date:
        comm_date = "04/04/2026"

    fs = rent_y_info.get("fs", 12.0)

    # Latimea paginii pentru a pozitiona textul in dreapta
    pw = pg.rect.width
    RIGHT_X = pw - 343  # x-ul de start pentru textul din dreapta

    # Gaseste linia Rent (ancora principala)
    rent_span = _find_span(pg, "900.00")
    ry = rent_y_info.get("rent_y", 537.34)
    if rent_span:
        o = rent_span.get("origin")
        ry = o[1] if o else rent_span["bbox"][1] + (rent_span["bbox"][3] - rent_span["bbox"][1]) * 0.78

    # Gaseste linia Expiry date
    expiry_span = _find_span(pg, "04/04/2027")
    if not expiry_span:
        expiry_span = _find_span(pg, "Expiry date")
    if expiry_span:
        o = expiry_span.get("origin")
        ey = o[1] if o else expiry_span["bbox"][1] + (expiry_span["bbox"][3] - expiry_span["bbox"][1]) * 0.78
    else:
        ey = ry - 27.60  # fallback: o linie deasupra Rent

    # "First payment..." pe linia Expiry date, in dreapta (un rand mai jos)
    pg.insert_text((RIGHT_X, ey + 14),
                   f"    First payment made of \u00a3 {rent_amount} paid on {comm_date}",
                   fontsize=fs, fontname=FONT, color=(0, 0, 0))

    # "Deposit of..." pe linia Rent, in dreapta
    pg.insert_text((RIGHT_X, ry),
                   f"    Deposit of \u00a3 {rent_amount} paid on {comm_date}",
                   fontsize=fs, fontname=FONT, color=(0, 0, 0))

    print(f"[PAYMENT] OK | expiry_y={ey:.2f} rent_y={ry:.2f} x={RIGHT_X:.2f} | £{rent_amount}")


def fill_contract(data: dict) -> bytes:
    if not PDF_SOURCE.is_file(): raise FileNotFoundError(f"Nu gasesc: {PDF_SOURCE}")
    if not RECEIPT_PDF.is_file(): raise FileNotFoundError(f"Nu gasesc: {RECEIPT_PDF}")

    # ── STEP 1: fitz completeaza contractul + adauga receipt ──
    doc = fitz.open(PDF_SOURCE)
    try:
        # ── PRE-SCAN: Ancora pe "900.00" = linia Rent din template ──
        pg2 = doc[1]
        rent_span = _find_span(pg2, "900.00")
        if rent_span:
            origin = rent_span.get("origin")
            ry = origin[1] if origin else (rent_span["bbox"][1] + (rent_span["bbox"][3] - rent_span["bbox"][1]) * 0.78)
            _rent_y_info = {"rent_y": ry, "x": rent_span["bbox"][0], "fs": rent_span.get("size", 12.0)}
            print(f"[PAYMENT LINES] Ancora Rent '900.00': y={ry:.2f} x={_rent_y_info['x']:.2f}")
        else:
            _rent_y_info = {"rent_y": 592.54, "x": 56.64, "fs": 12.0}
            print("[PAYMENT LINES] Ancora MISS — fallback rent_y=592.54")
        pg12=doc[11]
        for old in ["04/04/2026","04/04/2027"]:
            for block in pg12.get_text("dict")["blocks"]:
                if block.get("type")!=0: continue
                for line in block["lines"]:
                    if old in "".join(s["text"] for s in line["spans"]):
                        x0=min(s["bbox"][0] for s in line["spans"]); y0=min(s["bbox"][1] for s in line["spans"])
                        x1=max(s["bbox"][2] for s in line["spans"]); y1=max(s["bbox"][3] for s in line["spans"])
                        pg12.add_redact_annot(fitz.Rect(x0-1,y0-1,x1+1,y1+1),fill=(1,1,1))
        pg12.apply_redactions()
        for key,cfg in FIELDS.items():
            val=(data.get(key) or "").strip()
            if not val: continue
            pg=doc[cfg["page"]]
            if "point" in cfg: _insert_pt(pg,cfg["point"],val)
            elif "replace" in cfg:
                if not _replace_txt(pg,cfg["replace"],val): _insert(pg,cfg["replace"],val)
            else: _insert(pg,cfg["label"],val,cfg.get("y_min"),cfg.get("y_max"),cfg.get("gap",LABEL_GAP),cfg.get("fixed_x"))
        _append_receipt(doc, data)
        _append_british_gas(doc, data)
        _append_ni_letter(doc, data)
        _append_electricity_bill(doc, data)
        _insert_payment_lines(doc, data, _rent_y_info)
        # Salvam in memorie si reincarcare — altfel get_text nu vede textul nou inserat
        _tmp_bytes = doc.tobytes()
        doc.close()
        doc = fitz.open("pdf", _tmp_bytes)
        # Acum get_text vede si liniile First payment + Deposit => chenarul se extinde corect
        _widen_boxes_page2(doc)
        pdf_bytes = doc.tobytes()
    finally:
        doc.close()

    # ── STEP 2: pikepdf sterge logo din ultima pagina (alb) ──
    try:
        white_jpeg = _make_white_jpeg()
        pdf_bytes  = _replace_logo_in_pdf(pdf_bytes, "", white_jpeg)
    except Exception as e:
        import traceback
        print(f"[LOGO] EROARE sterge logo (ultima pagina): {e}")
        traceback.print_exc()

    # ── STEP 3: pikepdf sterge logo Howkins Harrison din pagina 13 (Rent Receipt, alb) ──
    try:
        white_jpeg = _make_white_jpeg()
        pdf_bytes  = _replace_logo_in_pdf(pdf_bytes, "", white_jpeg, page_index=12)
    except Exception as e:
        import traceback
        print(f"[LOGO] EROARE sterge logo pagina 13: {e}")
        traceback.print_exc()

    return pdf_bytes

def search_real_agents(city):
    client=anthropic.Anthropic()
    prompt=(f"Search for real letting/estate agents in {city}, UK. Find 4-5 agents. "
            f"Return ONLY JSON array: [{{\"name\":\"...\",\"address\":\"...\",\"phone\":\"...\",\"email\":\"...\"}}]")
    resp=client.messages.create(model="claude-sonnet-4-20250514",max_tokens=1500,
         tools=[{"type":"web_search_20250305","name":"web_search"}],
         messages=[{"role":"user","content":prompt}])
    text=" ".join(b.text for b in resp.content if hasattr(b,"text"))
    m=re.search(r"\[.*?\]",text,re.DOTALL)
    if not m: raise ValueError("Nu s-au gasit agenti.")
    return json.loads(m.group(0))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): return
    def _send(self,code,body,ct,dl=None):
        self.send_response(code)
        self.send_header("Content-Type",ct)
        self.send_header("X-Contract-Tool-Version",VERSION)
        if dl: self.send_header("Content-Disposition",f'attachment; filename="{dl}"')
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/proxy-logo":
            from urllib.parse import parse_qs,urlparse as _u
            qs=parse_qs(_u(self.path).query)
            url=(qs.get("url") or [""])[0]
            if not url.startswith("https://"):
                self._send(400,b"bad","text/plain"); return
            try:
                import urllib.request,base64
                with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=8) as r:
                    b=r.read(); ct=r.headers.get("Content-Type","image/png").split(";")[0]
                self._send(200,json.dumps({"b64":f"data:{ct};base64,{base64.b64encode(b).decode()}"}).encode(),"application/json")
            except Exception as e:
                self._send(500,json.dumps({"error":str(e)}).encode(),"application/json")
            return
        if path in ("","/"): path="/index.html"
        fp=(DIR/path.lstrip("/")).resolve()
        if not str(fp).startswith(str(DIR)) or not fp.is_file():
            self._send(404,b"Not found","text/plain"); return
        cmap={".html":"text/html; charset=utf-8",".css":"text/css",".js":"application/javascript",".png":"image/png"}
        body=fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",cmap.get(fp.suffix,"application/octet-stream"))
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Access-Control-Allow-Origin","*")
        if fp.suffix==".html":
            self.send_header("Cache-Control","no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma","no-cache")
        else:
            self.send_header("Cache-Control","no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError):
            pass  # Browser a inchis conexiunea - normal pe Windows
    def do_POST(self):
        path=urlparse(self.path).path
        length=int(self.headers.get("Content-Length",0))
        raw=self.rfile.read(length) if length else b"{}"
        if path=="/search-agent":
            try:
                body=json.loads(raw.decode()); city=body.get("city","").strip()
                if not city: self._send(400,json.dumps({"error":"Oras lipsa"}).encode(),"application/json"); return
                self._send(200,json.dumps({"agents":search_real_agents(city)}).encode(),"application/json")
            except Exception as e:
                self._send(500,json.dumps({"error":str(e)}).encode(),"application/json")
            return
        if path!="/generate":
            self._send(404,b"Not found","text/plain"); return
        try: data=json.loads(raw.decode())
        except: self._send(400,b"JSON invalid","text/plain"); return
        print(f"\n[REQUEST] agent_logo_b64: {'DA '+str(len(data.get('agent_logo_b64','')))+'chars' if data.get('agent_logo_b64') else 'NU'}")
        print(f"[REQUEST] landlord_address: {data.get('landlord_address','')[:60]}")
        try:
            pdf=fill_contract(data)
        except FileNotFoundError as e:
            self._send(404,str(e).encode(),"text/plain"); return
        except Exception as e:
            import traceback; traceback.print_exc()
            self._send(500,f"Eroare: {e}".encode(),"text/plain"); return
        self._send(200,pdf,"application/pdf","contract-completat.pdf")
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

def main():
    port=int(os.environ.get("PORT", sys.argv[1] if len(sys.argv)>1 else 8765))
    if not PDF_SOURCE.is_file():
        print(f"EROARE: {PDF_SOURCE}"); sys.exit(1)
    server=HTTPServer(("0.0.0.0",port),Handler)
    url=f"http://127.0.0.1:{port}/"
    print("="*60)
    print(f"  Contract tool v{VERSION}")
    print(f"  Logo AUTOMAT din landlord_address - MEREU activ")
    print("="*60)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nOprit.")

if __name__=="__main__":
    main()
