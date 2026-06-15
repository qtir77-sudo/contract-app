#!/usr/bin/env python3
"""Contract tool v5.7 - logo replace 100% functional"""
from __future__ import annotations
import json, sys, io, re, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse
import fitz
import anthropic

DIR         = Path(__file__).resolve().parent
PDF_SOURCE  = DIR / "test_contract_saca.pdf"

# ── Smart UK address splitter ─────────────────────────────────────────────────
def _split_uk_address(addr: str) -> list[str]:
    """Imparte o adresa UK in linii separate (nr+strada, oras, postcode).
    Functioneaza cu sau fara virgule. Numarul casei e MEREU pe aceeasi linie cu strada."""
    if not addr:
        return []
    # Daca are virgule, split simplu
    if "," in addr:
        parts = [p.strip() for p in addr.split(",") if p.strip()]
        # Combina primul element (nr) cu al doilea (strada) daca primul e doar un numar
        if len(parts) >= 2 and re.match(r'^\d+[A-Za-z]?$', parts[0]):
            parts = [parts[0] + ' ' + parts[1]] + parts[2:]
        return parts
    # Cauta postcode-ul UK la final (ex: CF1 2DD, SW1A 1AA, M1 1AE)
    m = re.search(r'\b([A-Z]{1,2}[0-9][0-9A-Z]?\s+[0-9][A-Z]{2})\s*$', addr.strip(), re.IGNORECASE)
    if m:
        postcode = m.group(1).upper()
        rest = addr[:m.start()].strip()
        words = rest.split()
        # Sufixe de strada comune
        suffixes = {'st','street','road','rd','avenue','ave','lane','ln','drive','dr',
                    'close','cl','way','court','ct','place','pl','grove','crescent','cres',
                    'terrace','ter','gardens','gdns','square','sq','row','hill','park','walk'}
        street_end = len(words)  # default: tot e strada
        for j, w in enumerate(words):
            if w.lower() in suffixes and j < len(words) - 1:
                street_end = j + 1
                break
        if street_end < len(words):
            street = ' '.join(words[:street_end])
            city   = ' '.join(words[street_end:])
            return [p for p in [street, city, postcode] if p]
        return [p for p in [rest, postcode] if p]
    # Niciun postcode gasit - returneaza ca o singura linie
    return [addr.strip()]
RECEIPT_PDF      = DIR / "adaugare_ppayscript.pdf"
BRITISH_GAS_PDF  = DIR / "british_gas_statement.pdf"
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

def _replace_logo_in_pdf(pdf_bytes: bytes, agent_display_name: str, logo_jpeg: bytes | None = None) -> bytes:
    """Inlocuieste /FXX3 in ultima pagina a PDF-ului cu logo-ul agentului."""
    import pikepdf as _pk
    if logo_jpeg is None:
        logo_jpeg = _make_logo_jpeg(agent_display_name)
    print(f"[LOGO] Inlocuiesc logo pentru '{agent_display_name}': {len(logo_jpeg)} bytes")
    pk = _pk.open(io.BytesIO(pdf_bytes))
    page = pk.pages[-1]
    xobj = page["/Resources"]["/XObject"]
    keys = list(xobj.keys())
    print(f"[LOGO] XObjects in ultima pagina: {keys}")
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

    print(f"[BRITISH GAS] OK | font={'Arial' if fontfile else 'helv'} {RS}pt | '{tenant}'")


def _append_ni_letter(doc, data):
    """Adauga scrisoarea National Insurance (HMRC) la final si inlocuieste datele chiriasului."""
    NI_LETTER_PDF = DIR / "ni_letter.pdf"
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
        print(f"[LOGO] EROARE sterge logo: {e}")
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
    port=int(os.environ.get("PORT") or 8080)
    if not PDF_SOURCE.is_file():
    server=HTTPServer(("0.0.0.0",port),Handler)
    url=f"http://0.0.0.0:{port}/"
    print("="*60)
    print(f"  Contract tool v{VERSION}")
    print(f"  Logo AUTOMAT din landlord_address - MEREU activ")
    print("="*60)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nOprit.")

if __name__=="__main__":
    main()
