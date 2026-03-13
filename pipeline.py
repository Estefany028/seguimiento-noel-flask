# pipeline.py
import os
import re
import time
from io import BytesIO
from datetime import datetime, date, time as dtime
from decimal import Decimal, InvalidOperation

import openpyxl
from dotenv import load_dotenv
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from google_client import sheets_service, drive_service, docs_service
from validators import extraer_file_id, leer_texto_pdf_desde_drive, extraer_fecha_pago_desde_pdf_texto

load_dotenv()

# =============================
# CACHE PARA GOOGLE SHEETS
# =============================

_CACHE = {}
_CACHE_TTL = 30


def _cache_get(key):
    item = _CACHE.get(key)
    if not item:
        return None

    value, ts = item

    if time.time() - ts > _CACHE_TTL:
        del _CACHE[key]
        return None

    return value


def _cache_set(key, value):
    _CACHE[key] = (value, time.time())


# =============================
# CACHE MAPAS
# =============================

_MAP_CACHE = {}
_MAP_CACHE_TTL = 120


def _map_cache_get(key):

    item = _MAP_CACHE.get(key)

    if not item:
        return None

    value, ts = item

    if time.time() - ts > _MAP_CACHE_TTL:
        del _MAP_CACHE[key]
        return None

    return value


def _map_cache_set(key, value):
    _MAP_CACHE[key] = (value, time.time())


# =============================
# CACHE PDF
# =============================

_PDF_CACHE = {}
_PDF_CACHE_TTL = 300


def _pdf_cache_get(file_id):

    item = _PDF_CACHE.get(file_id)

    if not item:
        return None

    texto, ts = item

    if time.time() - ts > _PDF_CACHE_TTL:
        del _PDF_CACHE[file_id]
        return None

    return texto


def _pdf_cache_set(file_id, texto):
    _PDF_CACHE[file_id] = (texto, time.time())


# =============================
# helpers
# =============================

def norm_digits(v) -> str:

    if v is None:
        return ""

    s = str(v).strip()

    if s.endswith(".0"):
        s = s[:-2]

    if "e" in s.lower():
        try:
            s = format(Decimal(s), "f")
        except InvalidOperation:
            pass

    return re.sub(r"\D", "", s)


# =============================
# fechas
# =============================

def parse_ts_form(s: str) -> datetime | None:

    if not s:
        return None

    s = str(s).strip()

    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass

    return None


def parse_date_any(s: str) -> date | None:

    if not s:
        return None

    s = str(s).strip()

    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        s = m.group(1)

    parts = re.split(r"[/-]", s)

    if len(parts) == 3:
        p1, p2, p3 = parts

        if p1.isdigit() and p2.isdigit() and p3.isdigit():

            if int(p1) <= 12 and int(p2) > 12:
                try:
                    return date(int(p3), int(p1), int(p2))
                except:
                    pass

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except:
            pass

    return None


SPANISH_MONTH = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12
}

# =============================
# CALENDARIO PAGOS SS
# =============================

def parse_range_ult2(s):

    if not s:
        return None

    s = str(s).lower().strip()

    m = re.search(r"(\d{1,2})\s*(?:-|al|a)\s*(\d{1,2})", s)

    if not m:
        return None

    return int(m.group(1)), int(m.group(2))


def _parse_day_month_cell(s):

    if not s:
        return None

    s = str(s).strip().lower()

    m = re.search(r"(\d{1,2})\s*de\s*([a-záéíóúñ]+)", s)

    if not m:
        return None

    day = int(m.group(1))
    mon_name = m.group(2)

    mon = SPANISH_MONTH.get(mon_name)

    if not mon:
        return None

    return day, mon


def _parse_header_mes_pagado(header):

    if not header:
        return None

    h = str(header).strip().lower()

    # busca "mes año" en cualquier parte del texto
    m = re.search(r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(\d{4})", h)

    if not m:
        return None

    mon = SPANISH_MONTH.get(m.group(1))

    if not mon:
        return None

    yr = int(m.group(2))

    return yr, mon


def load_calendario_tabla():

    base_id = os.getenv("SPREADSHEET_BASE_ID")

    cal_name = os.getenv("SHEET_CAL_NAME", "Fechas de pago")

    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    svc = sheets_service()

    values = _values_get(svc, base_id, f"{cal_name}!A1:N")

    if not values or len(values) < 2:
        return {}

    headers = values[0]
    body = values[1:]

    mes_cols = []

    for j in range(2, len(headers)):

        key = _parse_header_mes_pagado(headers[j])

        if key:
            yr, mon = key
            mes_cols.append((j, yr, mon))

    calendario = {}

    for row in body:

        if not row:
            continue

        rg = parse_range_ult2(row[0])

        if not rg:
            continue

        mn, mx = rg

        for (j, yr, mon) in mes_cols:

            cell = row[j] if j < len(row) else ""

            dm = _parse_day_month_cell(cell)

            if not dm:
                continue

            day, month_venc = dm

            calendario.setdefault((yr, mon), []).append({
                "min": mn,
                "max": mx,
                "day": day,
                "month": month_venc
            })

    return calendario

# =============================
# SHEETS HELPERS
# =============================

def _values_get(svc, spreadsheet_id: str, range_a1: str):

    cache_key = f"{spreadsheet_id}:{range_a1}"

    cached = _cache_get(cache_key)

    if cached is not None:
        return cached

    result = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueRenderOption="FORMATTED_VALUE"
    ).execute().get("values", [])

    _cache_set(cache_key, result)

    return result

def _values_append(svc, spreadsheet_id: str, range_a1: str, rows):

    result = svc.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows}
    ).execute()

    _CACHE.clear()
    _MAP_CACHE.clear()

    return result


def _values_batch_update(svc, spreadsheet_id: str, updates):

    data = [{"range": r, "values": v} for (r, v) in updates]

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": data
        }
    ).execute()

    _CACHE.clear()
    _MAP_CACHE.clear()


# =============================
# XLSX
# =============================

def download_drive_file_bytes(file_id: str):

    drive = drive_service()

    try:
        drive.files().get(
            fileId=file_id,
            supportsAllDrives=True,
            fields="id,name,mimeType,driveId"
        ).execute()

    except HttpError as e:
        raise RuntimeError(f"No pude leer metadata del archivo {file_id}. {e}")

    request = drive.files().get_media(
        fileId=file_id,
        supportsAllDrives=True
    )

    fh = BytesIO()

    downloader = MediaIoBaseDownload(fh, request)

    done = False

    while not done:
        _, done = downloader.next_chunk()

    return fh.getvalue()

def _cell_to_sheet_value(v):

    if v is None:
        return ""

    if isinstance(v, datetime):

        if v.hour == 0 and v.minute == 0 and v.second == 0:
            return v.strftime("%d/%m/%Y")

        return v.strftime("%d/%m/%Y %H:%M:%S")

    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")

    if isinstance(v, dtime):
        return v.strftime("%H:%M:%S")

    return v


def extract_rows_from_xlsx(xlsx_bytes, start_row=11):

    wb = openpyxl.load_workbook(
        filename=BytesIO(xlsx_bytes),
        data_only=True
    )

    ws = wb.worksheets[0]

    out = []

    for r in ws.iter_rows(min_row=start_row, values_only=True):

        row = [_cell_to_sheet_value(v) for v in r]

        if any(str(c).strip() for c in row):
            out.append(row)

    return out


# =============================
# VALIDACIONES
# =============================

def build_cert_map():

    cached = _map_cache_get("cert_map")
    if cached:
        return cached

    cert_db_id = os.getenv("CERT_DB_ID")

    svc = sheets_service()

    values = _values_get(svc, cert_db_id, "A:E")

    rows = values[1:]

    m = {}

    for r in rows:

        if len(r) < 5:
            continue

        cc = norm_digits(r[0])

        ts = parse_ts_form(r[1]) or datetime.min

        fecha_ind = parse_date_any(r[2])

        link_ss = str(r[4]).strip()

        if not cc:
            continue

        if cc not in m or ts > m[cc]["ts"]:
            m[cc] = {
                "ts": ts,
                "fecha_ind": fecha_ind,
                "link_ss": link_ss
            }

    _map_cache_set("cert_map", m)

    return m


def build_ind_map():

    cached = _map_cache_get("ind_map")

    if cached:
        return cached

    ind_db_id = os.getenv("IND_DB_ID")

    svc = sheets_service()

    values = _values_get(svc, ind_db_id, "A:K")

    rows = values[1:]

    out = {}

    for r in rows:

        if len(r) < 6:
            continue

        cc = norm_digits(r[5])

        d = parse_date_any(r[2])

        if not cc or not d:
            continue

        if cc not in out or d > out[cc]:
            out[cc] = d

    _map_cache_set("ind_map", out)

    return out


def validar_y_escribir_filas(base_start_row, num_rows):

    base_id = os.getenv("SPREADSHEET_BASE_ID")

    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    svc = sheets_service()

    drive = drive_service()

    docs = docs_service()

    headers = _values_get(
        svc,
        base_id,
        f"{base_name}!A1:AE1"
    )[0]

    idx_ced = next((i for i, h in enumerate(headers) if "CEDUL" in str(h).upper()), 14)

    idx_nit = next((i for i, h in enumerate(headers) if "NIT" in str(h).upper()), 9)

    end_row = base_start_row + num_rows - 1

    rows = _values_get(
        svc,
        base_id,
        f"{base_name}!A{base_start_row}:AE{end_row}"
    )

    cert_map = build_cert_map()

    ind_map = build_ind_map()

    calendario = load_calendario_tabla()

    hoy = date.today()

    out_ind = []
    out_fecha = []
    out_leido = []
    out_vigss = []
    out_venc = []

    for r in rows:

        cc = norm_digits(r[idx_ced])

        nit = norm_digits(r[idx_nit])

        fecha_ind = ind_map.get(cc)

        if fecha_ind:

            dias = (hoy - fecha_ind).days

            out_ind.append(["VIGENTE" if dias <= 365 else "VENCIDA"])

        else:

            out_ind.append(["SIN REGISTRO"])

        if cc not in cert_map:

            out_fecha.append([""])

            out_leido.append(["NO LEÍDO"])

            out_vigss.append(["REVISAR"])

            out_venc.append([""])

            continue

        pdf_id = extraer_file_id(cert_map[cc]["link_ss"])

        texto = _pdf_cache_get(pdf_id)

        if texto is None:

            texto = leer_texto_pdf_desde_drive(
                drive,
                docs,
                pdf_id
            )

            _pdf_cache_set(pdf_id, texto)

        fecha_txt = extraer_fecha_pago_desde_pdf_texto(texto)

        fp = parse_date_any(fecha_txt)

        if not fp:

            out_fecha.append([""])

            out_leido.append(["NO LEÍDO"])

            out_vigss.append(["REVISAR"])

            out_venc.append([""])

            continue

        out_fecha.append([fp.strftime("%d/%m/%Y")])

        out_leido.append(["OK"])

        # --- calcular mes pagado ---
        if fp.month == 1:
            mes_pagado = 12
            anio_mes_pagado = fp.year - 1
        else:
            mes_pagado = fp.month - 1
            anio_mes_pagado = fp.year

        # mes siguiente al pagado → determina la vigencia
        mes_vigencia = mes_pagado + 1
        anio_vigencia = anio_mes_pagado

        if mes_vigencia == 13:
            mes_vigencia = 1
            anio_vigencia += 1

        reglas_mes = calendario.get((anio_vigencia, mes_vigencia), [])

        # calcular ultimos 2 del NIT
        ult2 = None
        if nit:
            digits = re.sub(r"\D", "", nit)
            if len(digits) >= 2:
                ult2 = int(digits[-2:])

        ult2 = None

        if nit:
            digits = re.sub(r"\D", "", nit)

            if len(digits) >= 2:
                ult2 = int(digits[-2:])

        regla = None
        if ult2 is not None:
            for rg in reglas_mes:
                if rg["min"] <= ult2 <= rg["max"]:
                    regla = rg
                    break

        if not regla:
            out_vigss.append(["REVISAR"])
            out_venc.append([""])
            continue

        # año del vencimiento
        anio_venc = anio_vigencia

        limite = date(anio_vigencia, regla["month"], regla["day"])

        out_venc.append([limite.strftime("%d/%m/%Y")])

        # validar contra fecha actual
        if hoy <= limite:
            out_vigss.append(["VIGENTE"])
        else:
            out_vigss.append(["VENCIDA"])

    updates = [

        (f"{base_name}!AA{base_start_row}:AA{end_row}", out_ind),

        (f"{base_name}!AB{base_start_row}:AB{end_row}", out_fecha),

        (f"{base_name}!AC{base_start_row}:AC{end_row}", out_leido),

        (f"{base_name}!AD{base_start_row}:AD{end_row}", out_vigss),

        (f"{base_name}!AE{base_start_row}:AE{end_row}", out_venc)

    ]

    _values_batch_update(
        svc,
        base_id,
        updates
    )

def revalidar_activos_base():
    """
    Revalida SOLO filas activas:
    FECHA FIN >= hoy
    """

    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    svc = sheets_service()

    # buscar columna FECHA FIN
    headers_vals = _values_get(svc, base_id, f"{base_name}!A1:AE1")
    headers = headers_vals[0] if headers_vals else []

    idx_ffin = next(
        (i for i, h in enumerate(headers) if "FECHA FIN" in str(h).upper()),
        -1
    )

    if idx_ffin == -1:
        raise RuntimeError("No encontré la columna 'FECHA FIN'")

    data = _values_get(svc, base_id, f"{base_name}!A2:AE")

    if not data:
        return {"ok": True, "rows": 0}

    hoy = date.today()

    activos_rel = []

    for i, row in enumerate(data):

        ffin_raw = row[idx_ffin] if idx_ffin < len(row) else ""

        ffin = parse_date_any(ffin_raw)

        if not ffin:
            continue

        if ffin >= hoy:
            activos_rel.append(i)

    if not activos_rel:
        return {"ok": True, "rows": 0}

    activos_rel.sort()

    bloques = []

    start = activos_rel[0]
    prev = activos_rel[0]

    for x in activos_rel[1:]:

        if x == prev + 1:
            prev = x
        else:
            bloques.append((start, prev))
            start = prev = x

    bloques.append((start, prev))

    total = 0

    for a, b in bloques:

        base_start_row = 2 + a
        num_rows = (b - a) + 1

        validar_y_escribir_filas(base_start_row, num_rows)

        total += num_rows

    return {
        "ok": True,
        "rows": total,
        "bloques": len(bloques)
    }

def procesar_xlsx_link_y_validar(xlsx_url: str):

    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    file_id = extraer_file_id(xlsx_url)

    if not file_id:
        raise RuntimeError("No se pudo extraer fileId del XLSX")

    xlsx_bytes = download_drive_file_bytes(file_id)

    rows = extract_rows_from_xlsx(xlsx_bytes, start_row=11)

    if not rows:
        return {"inserted": 0}

    svc = sheets_service()

    resp = _values_append(
        svc,
        base_id,
        f"{base_name}!A2",
        rows
    )

    upd = resp.get("updates", {})

    updated_range = upd.get("updatedRange", "")

    m = re.search(r"!A(\d+):", updated_range)

    if not m:
        return {"inserted": len(rows)}

    start_row = int(m.group(1))

    validar_y_escribir_filas(
        start_row,
        len(rows)
    )

    return {
        "inserted": len(rows),
        "start_row": start_row
    }
