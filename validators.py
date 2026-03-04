# validators.py
import re
from io import BytesIO
from datetime import datetime, date
from googleapiclient.http import MediaIoBaseDownload

# PyMuPDF
try:
    import fitz  # pymupdf
except Exception:
    fitz = None

# fallback
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# ==========================
# Patrones (se conservan)
# ==========================
PATRONES_FECHA_PAGO = [
    # soporta: "PAGADA 2026-01-08 11:22:18.0", "PAGADO 08/01/2026", etc.
    re.compile(r"\bPAGAD[AO]\b[\s\S]{0,250}?(\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"\bPAGAD[AO]\b[\s\S]{0,250}?(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", re.I),

    re.compile(r"\bFECHA\s*DE\s*PAGO\b[\s\S]{0,250}?(\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"\bFECHA\s*DE\s*PAGO\b[\s\S]{0,250}?(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", re.I),

    re.compile(r"\bFecha\s*Pago\b[\s\S]{0,250}?(\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"\bFecha\s*Pago\b[\s\S]{0,250}?(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})", re.I),
]

# ==========================
# Utilidades (se conservan)
# ==========================
def extraer_file_id(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None

def _download_drive_bytes(drive, file_id: str) -> bytes:
    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return fh.getvalue()

def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    # 1) PyMuPDF
    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = " ".join((page.get_text("text") or "") for page in doc)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                return text
        except Exception:
            pass

    # 2) pypdf
    if PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            textos = [(p.extract_text() or "") for p in reader.pages]
            text = re.sub(r"\s+", " ", " ".join(textos)).strip()
            if text:
                return text
        except Exception:
            pass

    return ""

def _read_google_doc_text(docs, doc_id: str) -> str:
    """Lee texto plano del Google Doc via Docs API."""
    doc = docs.documents().get(documentId=doc_id).execute()
    out = []
    for el in doc.get("body", {}).get("content", []):
        p = el.get("paragraph")
        if not p:
            continue
        for r in p.get("elements", []):
            tr = r.get("textRun", {})
            if "content" in tr:
                out.append(tr["content"])
    return re.sub(r"\s+", " ", "".join(out)).strip()

def leer_texto_pdf_desde_drive(drive, docs, file_id: str) -> str:
    """
    Estrategia robusta:
    1) Descargar bytes PDF + extraer texto (pymupdf / pypdf)
    2) Si texto vacío, convertir PDF -> Google Doc y leer texto con Docs API
    """
    pdf_bytes = _download_drive_bytes(drive, file_id)
    text = _extract_text_from_pdf_bytes(pdf_bytes)

    if text:
        return text

    # Fallback: convertir PDF -> Google Doc (requiere scope drive)
    # Nota: esto crea un archivo temporal en Drive, luego lo borramos.
    copied = drive.files().copy(
        fileId=file_id,
        supportsAllDrives=True,
        body={"mimeType": "application/vnd.google-apps.document"}
    ).execute()

    doc_id = copied["id"]

    try:
        text = _read_google_doc_text(docs, doc_id)
        return text or ""
    finally:
        # borrar el doc temporal
        try:
            drive.files().delete(fileId=doc_id, supportsAllDrives=True).execute()
        except Exception:
            pass


# ==========================
# Extracción de fecha (mejorada)
# - Mantiene tu enfoque por keywords/patrones
# - Si hay varias fechas, elige la más "cercana" al keyword
#   y, en caso de empate, la más reciente.
# ==========================
_KEYWORDS = ["FECHA DE PAGO", "Fecha Pago", "PAGADO", "PAGADA"]

# captura fechas ISO o d/m/y (con / o -) y permite datetime pegado al ISO
_DATE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)?|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})"
)

def _parse_any_date(s: str) -> date | None:
    if not s:
        return None
    s = str(s).strip()

    # si viene "2026-01-08 11:22:18.0" -> "2026-01-08"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        s = m.group(1)

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def extraer_fecha_pago_desde_pdf_texto(texto: str) -> str | None:
    if not texto:
        return None

    t = re.sub(r"\s+", " ", texto)

    candidatos: list[tuple[int, date]] = []  # (score, date)

    # 1) Búsqueda por keywords + fecha cercana (robusta)
    for kw in _KEYWORDS:
        for mkw in re.finditer(re.escape(kw), t, flags=re.IGNORECASE):
            start = mkw.end()
            window = t[start:start + 300]  # ventana corta para evitar fechas de otras secciones
            md = _DATE_RE.search(window)
            if not md:
                continue

            raw = md.group(1)
            d = _parse_any_date(raw)
            if not d:
                continue

            dist = md.start()  # qué tan cerca está la fecha del keyword
            score = 10_000 - dist

            # bonus: prioriza explícitamente "FECHA DE PAGO" / "Fecha Pago"
            if kw.upper().replace("  ", " ") == "FECHA DE PAGO" or kw == "Fecha Pago":
                score += 2_000

            candidatos.append((score, d))

    if candidatos:
        candidatos.sort(key=lambda x: x[0], reverse=True)
        best_score = candidatos[0][0]

        # si hay varios con score muy parecido, elige la fecha más reciente entre esos top
        top = [c for c in candidatos if c[0] >= best_score - 50]
        best_date = max(c[1] for c in top)
        return best_date.strftime("%Y-%m-%d")

    # 2) Fallback: usa tus patrones originales (por compatibilidad)
    for p in PATRONES_FECHA_PAGO:
        m = p.search(t)
        if m and m.group(1):
            d = _parse_any_date(m.group(1))
            if d:
                return d.strftime("%Y-%m-%d")
            return m.group(1)

    return None
