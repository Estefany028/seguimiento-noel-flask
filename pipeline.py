# pipeline.py
import os
import re
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

# ===== fechas =====
def parse_ts_form(s: str) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

def parse_date_any(s: str) -> date | None:
    if not s:
        return None
    s = str(s).strip()

    # soporta "2026-01-08 11:22:18.0"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        s = m.group(1)

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

SPANISH_MONTH = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12
}

def parse_spanish_date_text(s: str) -> date | None:
    if not s:
        return None
    s = str(s).strip().lower()
    m = re.search(r"([a-záéíóúñ]+)\s+(\d{1,2})\s+de\s+(\d{4})", s)
    if not m:
        return None
    mon = SPANISH_MONTH.get(m.group(1))
    if not mon:
        return None
    return date(int(m.group(3)), mon, int(m.group(2)))

def parse_range_ult2(s: str) -> tuple[int, int] | None:
    if not s:
        return None
    m = re.search(r"(\d{1,2})\s*al\s*(\d{1,2})", str(s))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))

def _parse_day_month_cell(s: str) -> tuple[int, int] | None:
    """
    Convierte celdas del calendario como:
    "05 de enero", "3 de febrero" -> (day, month)
    """
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

def _parse_header_mes_pagado(header: str) -> tuple[int, int] | None:
    """
    Headers tipo:
    "Diciembre 2025 (pago en enero)"
    "Enero 2026 (pago en febrero)"
    => devuelve (anio_mes_pagado, mes_pagado)
    """
    if not header:
        return None
    h = str(header).strip().lower()
    m = re.search(r"^([a-záéíóúñ]+)\s+(\d{4})", h)
    if not m:
        return None
    mon = SPANISH_MONTH.get(m.group(1))
    if not mon:
        return None
    yr = int(m.group(2))
    return (yr, mon)

# ===== sheets helpers =====
def _values_get(svc, spreadsheet_id: str, range_a1: str):
    return svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])

def _values_append(svc, spreadsheet_id: str, range_a1: str, rows: list[list]):
    return svc.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

def _values_batch_update(svc, spreadsheet_id: str, updates: list[tuple[str, list[list]]]):
    data = [{"range": r, "values": v} for (r, v) in updates]
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()

# ===== xlsx =====
def download_drive_file_bytes(file_id: str) -> bytes:
    drive = drive_service()

    # metadata (debug permisos)
    try:
        drive.files().get(
            fileId=file_id,
            supportsAllDrives=True,
            fields="id,name,mimeType,driveId"
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"No pude leer metadata del archivo {file_id}. PERMISOS. Detalle: {e}")

    request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
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

def extract_rows_from_xlsx(xlsx_bytes: bytes, start_row: int = 11) -> list[list]:
    wb = openpyxl.load_workbook(filename=BytesIO(xlsx_bytes), data_only=True)
    ws = wb.worksheets[0]
    out = []
    for r in ws.iter_rows(min_row=start_row, values_only=True):
        row = [_cell_to_sheet_value(v) for v in r]
        if any(str(c).strip() for c in row):
            out.append(row)
    return out

# ===== VALIDACIONES =====
def build_cert_map() -> dict[str, dict]:
    cert_db_id = os.getenv("CERT_DB_ID")
    if not cert_db_id:
        raise RuntimeError("Falta CERT_DB_ID")

    svc = sheets_service()
    values = _values_get(svc, cert_db_id, "A:E")
    if not values:
        return {}

    rows = values[1:]
    m = {}
    for r in rows:
        if len(r) < 5:
            continue

        cc = norm_digits(r[0])
        ts = parse_ts_form(r[1]) or datetime.min

        # fecha inducción (formato viejo)
        fecha_ind = parse_date_any(r[2]) if len(r) > 2 else None

        link_ind = str(r[3]).strip() if len(r) > 3 else ""
        link_ss  = str(r[4]).strip() if len(r) > 4 else ""

        if not cc:
            continue

        # quedarnos con el registro más reciente (por timestamp)
        if cc not in m or ts > m[cc]["ts"]:
            m[cc] = {
                "ts": ts,
                "fecha_ind": fecha_ind,
                "link_ind": link_ind,
                "link_ss": link_ss
            }

    return m

def build_ind_map() -> dict[str, date]:
    ind_db_id = os.getenv("IND_DB_ID")
    if not ind_db_id:
        raise RuntimeError("Falta IND_DB_ID")

    svc = sheets_service()
    values = _values_get(svc, ind_db_id, "A:K")
    if not values:
        return {}

    rows = values[1:]
    out: dict[str, date] = {}
    for r in rows:
        if len(r) < 6:
            continue
        cc = norm_digits(r[5])
        d = parse_date_any(r[2])
        if not cc or not d:
            continue
        if cc not in out or d > out[cc]:
            out[cc] = d
    return out

def load_calendario_tabla() -> dict[tuple[int, int], list[dict]]:
    """
    Lee hoja "Fechas de pago" con headers A:N.
    Devuelve:
      calendario[(anio_mes_pagado, mes_pagado)] = [{min,max,day,month}, ...]
    Donde day/month salen de la celda tipo "22 de enero".
    """
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

    # columnas de meses desde C (index 2)
    mes_cols: list[tuple[int, int, int]] = []
    for j in range(2, len(headers)):
        key = _parse_header_mes_pagado(headers[j])
        if key:
            yr, mon = key
            mes_cols.append((j, yr, mon))

    calendario: dict[tuple[int, int], list[dict]] = {}

    for row in body:
        if not row or len(row) < 1:
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

def validar_y_escribir_filas(base_start_row: int, num_rows: int):
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")
    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    svc = sheets_service()
    drive = drive_service()
    docs = docs_service()

    headers_vals = _values_get(svc, base_id, f"{base_name}!A1:AE1")
    headers = headers_vals[0] if headers_vals else []

    idx_ced = next((i for i, h in enumerate(headers) if "CEDUL" in str(h).upper()), 14)
    idx_nit = next((i for i, h in enumerate(headers) if "NIT" in str(h).upper()), 9)

    end_row = base_start_row + num_rows - 1
    rows = _values_get(svc, base_id, f"{base_name}!A{base_start_row}:AE{end_row}")

    cert_map = build_cert_map()
    ind_map = build_ind_map()
    calendario = load_calendario_tabla()

    hoy = date.today()
    vig_dias = 365

    # 👇 Z (CERTIFICADOS) eliminado
    out_ind = []
    out_fecha, out_leido, out_vigss, out_venc = [], [], [], []

    for r in rows:
        cc = norm_digits(r[idx_ced] if idx_ced < len(r) else "")
        nit = norm_digits(r[idx_nit] if idx_nit < len(r) else "")

        # INDUCCIÓN (1) BD NUEVA (IND_DB_ID) (2) fallback BD CERTIFICADOS (CERT_DB_ID)
        fecha_ind = None
        if cc and cc in ind_map:
            fecha_ind = ind_map[cc]
        elif cc and cc in cert_map:
            fecha_ind = cert_map[cc].get("fecha_ind")

        if fecha_ind:
            dias = (hoy - fecha_ind).days
            out_ind.append(["VIGENTE" if dias <= vig_dias else "VENCIDA"])
        else:
            out_ind.append(["SIN REGISTRO"])

        # SS
        if not cc or not nit or cc not in cert_map or not cert_map[cc]["link_ss"]:
            out_fecha.append([""])
            out_leido.append(["NO LEÍDO"])
            out_vigss.append(["REVISAR"])
            out_venc.append([""])
            continue

        pdf_id = extraer_file_id(cert_map[cc]["link_ss"])
        if not pdf_id:
            out_fecha.append([""])
            out_leido.append(["LINK INVÁLIDO"])
            out_vigss.append(["REVISAR"])
            out_venc.append([""])
            continue

        texto = leer_texto_pdf_desde_drive(drive, docs, pdf_id)
        fecha_txt = extraer_fecha_pago_desde_pdf_texto(texto)

        if not texto or not fecha_txt:
            out_fecha.append([""])
            out_leido.append(["NO LEÍDO"])
            out_vigss.append(["REVISAR"])
            out_venc.append([""])
            continue

        fp = parse_date_any(fecha_txt)
        if not fp:
            out_fecha.append([""])
            out_leido.append(["NO LEÍDO"])
            out_vigss.append(["REVISAR"])
            out_venc.append([""])
            continue

        out_fecha.append([fp.strftime("%d/%m/%Y")])
        out_leido.append(["OK"])

        # --- mes pagado (mes vencido) ---
        if fp.month == 1:
            mes_pagado = 12
            anio_mes_pagado = fp.year - 1
        else:
            mes_pagado = fp.month - 1
            anio_mes_pagado = fp.year

        reglas_mes = calendario.get((anio_mes_pagado, mes_pagado), [])

        ult2 = int(nit[-2:]) if len(nit) >= 2 and nit[-2:].isdigit() else None
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

        # año del vencimiento (normalmente es el año del pago)
        anio_venc = fp.year
        if fp.month == 12 and regla["month"] == 1:
            anio_venc = fp.year + 1
        elif fp.month == 1 and regla["month"] == 12:
            anio_venc = fp.year - 1

        limite = date(anio_venc, regla["month"], regla["day"])
        out_venc.append([limite.strftime("%d/%m/%Y")])

        out_vigss.append(["VIGENTE" if fp <= limite else "VENCIDA"])

    # 👇 updates: Z eliminado, empieza en AA
    updates = [
        (f"{base_name}!AA{base_start_row}:AA{end_row}", out_ind),
        (f"{base_name}!AB{base_start_row}:AB{end_row}", out_fecha),
        (f"{base_name}!AC{base_start_row}:AC{end_row}", out_leido),
        (f"{base_name}!AD{base_start_row}:AD{end_row}", out_vigss),
        (f"{base_name}!AE{base_start_row}:AE{end_row}", out_venc),
    ]
    _values_batch_update(svc, base_id, updates)

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

    # IMPORTANTE: append desde A2 para no tocar encabezados
    resp = _values_append(svc, base_id, f"{base_name}!A2", rows)

    upd = resp.get("updates", {})
    updated_range = upd.get("updatedRange", "")
    m = re.search(r"!A(\d+):", updated_range)
    if not m:
        return {"inserted": len(rows), "updatedRange": updated_range}

    start_row = int(m.group(1))
    validar_y_escribir_filas(start_row, len(rows))
    return {"inserted": len(rows), "start_row": start_row, "updatedRange": updated_range}

def revalidar_todo_base():
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")
    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    svc = sheets_service()

    # saber cuántas filas hay (leyendo A:A)
    colA = _values_get(svc, base_id, f"{base_name}!A:A")
    last_row = len(colA)  # incluye encabezado

    if last_row < 2:
        return {"ok": True, "rows": 0}

    start_row = 2
    num_rows = last_row - 1

    validar_y_escribir_filas(start_row, num_rows)
    return {"ok": True, "rows": num_rows}

def revalidar_activos_base():
    """
    Revalida SOLO filas activas:
    FECHA FIN >= hoy
    (reduce mucho el tiempo vs revalidar todo)
    """
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")
    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    svc = sheets_service()

    # Leer encabezados para ubicar columna FECHA FIN
    headers_vals = _values_get(svc, base_id, f"{base_name}!A1:AE1")
    headers = headers_vals[0] if headers_vals else []
    idx_ffin = next((i for i, h in enumerate(headers) if "FECHA FIN" == str(h).strip().upper()), -1)
    if idx_ffin == -1:
        # fallback si cambia el header o viene con saltos/espacios
        idx_ffin = next((i for i, h in enumerate(headers) if "FECHA FIN" in str(h).upper()), -1)

    if idx_ffin == -1:
        raise RuntimeError("No encontré la columna 'FECHA FIN' en Base_Personas")

    # Leer FECHA FIN + una columna que siempre tenga contenido para saber cuántas filas hay
    # (A:A suele estar llena si FECHA también existe)
    data = _values_get(svc, base_id, f"{base_name}!A2:AE")
    if not data:
        return {"ok": True, "rows": 0, "detalle": "No hay filas"}

    hoy = date.today()

    # identificar filas activas por índice relativo
    activos_rel = []
    for i, row in enumerate(data):  # i=0 corresponde a fila 2
        ffin_raw = row[idx_ffin] if idx_ffin < len(row) else ""
        ffin = parse_date_any(ffin_raw)
        if not ffin:
            continue
        if ffin >= hoy:
            activos_rel.append(i)

    if not activos_rel:
        return {"ok": True, "rows": 0, "detalle": "No hay activos para revalidar"}

    # Revalidar en “bloques contiguos” para hacer pocas llamadas
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

    return {"ok": True, "rows": total, "bloques": len(bloques)}
