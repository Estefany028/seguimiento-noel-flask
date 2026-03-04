# services.py
import os
from datetime import datetime, date
from google_client import sheets_service

def _hoy_date():
    return date.today()

def _parse_sheet_date(val):
    if val in (None, ""):
        return None
    s = str(val).strip()
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def read_sheet_values(spreadsheet_id: str, range_a1: str):
    svc = sheets_service()
    resp = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueRenderOption="FORMATTED_VALUE"
    ).execute()
    return resp.get("values", [])

def write_sheet_value(spreadsheet_id: str, range_a1: str, value):
    svc = sheets_service()
    body = {"values": [[value]]}
    svc.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_a1,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

def obtener_personas_vigentes_externo():
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID en .env")

    values = read_sheet_values(base_id, f"{base_name}!A1:AE")
    if not values:
        return []

    headers = values[0]
    rows = values[1:]

    def idx(name):
        try:
            return headers.index(name)
        except Exception:
            return -1

    idx_nombre = idx("NOMBRES")
    idx_apellido = idx("APELLIDOS")
    idx_empresa = idx("EMPRESA")
    idx_cedula = next((i for i, h in enumerate(headers) if "CEDUL" in str(h).upper()), -1)

    idx_fecha_fin = idx("FECHA FIN")
    if idx_fecha_fin == -1:
        idx_fecha_fin = 21  # fallback (col V)

    # SOLO INDUCCION + SS (según tu pipeline: AA y AD)
    COL_IND  = 26  # AA
    COL_SS   = 29  # AD

    hoy = _hoy_date()
    out = []

    for r in rows:
        if idx_cedula < 0 or idx_cedula >= len(r) or not r[idx_cedula]:
            continue

        fin = _parse_sheet_date(r[idx_fecha_fin]) if idx_fecha_fin < len(r) else None
        if not fin or fin < hoy:
            continue

        induccion = r[COL_IND] if COL_IND < len(r) else ""
        seguridad = r[COL_SS] if COL_SS < len(r) else ""

        motivos = []
        if induccion != "VIGENTE":
            motivos.append("Inducción vencida o no registrada")
        if seguridad != "VIGENTE":
            motivos.append("Seguridad Social vencida")

        estado = "CUMPLE" if not motivos else "REVISAR"

        out.append({
            "nombre": f"{r[idx_nombre] if idx_nombre!=-1 else ''} {r[idx_apellido] if idx_apellido!=-1 else ''}".strip(),
            "cedula": r[idx_cedula],
            "empresa": r[idx_empresa] if idx_empresa!=-1 else "",
            "induccion": induccion,
            "seguridadSocial": seguridad,
            "estado": estado,
            "motivo": " · ".join(motivos)
        })

    return out

def obtener_solicitudes_admin():
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID en .env")

    values = read_sheet_values(base_id, f"{base_name}!A1:AE")
    if not values:
        return []

    headers = values[0]
    rows = values[1:]
    hoy = _hoy_date()

    def idx(name):
        try:
            return headers.index(name)
        except Exception:
            return -1

    idx_empresa = idx("EMPRESA")
    idx_nit = next((i for i, h in enumerate(headers) if "NIT" in str(h).upper()), -1)

    idx_hora_ing = idx("HORA INGRESO")
    idx_hora_sal = idx("HORA SALIDA")
    idx_tipo = idx("TIPO DE TRABAJO")
    idx_ext = idx("EXTENSION")
    idx_interv = idx("INTERVENTOR")
    idx_turno = idx("TURNO")
    idx_fini = idx("FECHA DE INICIO")
    idx_ffin = idx("FECHA FIN")
    if idx_ffin == -1:
        idx_ffin = 21

    idx_nombre = idx("NOMBRES")
    idx_apellido = idx("APELLIDOS")
    idx_cedula = next((i for i, h in enumerate(headers) if "CEDUL" in str(h).upper()), -1)

    idx_consec = idx("CONSECUTIVO")
    if idx_consec == -1:
        idx_consec = 23  # fallback

    # SOLO INDUCCION + SS
    COL_IND  = 26  # AA
    COL_SS   = 29  # AD

    solicitudes = {}

    def safe_get(row, i):
        if i is None or i < 0 or i >= len(row):
            return ""
        v = row[i]
        return "" if v is None else str(v).strip()

    for sheet_row, r in enumerate(rows, start=2):
        if idx_cedula == -1 or idx_cedula >= len(r) or not r[idx_cedula]:
            continue

        fin = _parse_sheet_date(r[idx_ffin]) if idx_ffin < len(r) else None
        if not fin or fin < hoy:
            continue

        empresa = safe_get(r, idx_empresa)
        nit = safe_get(r, idx_nit)
        hora_ing = safe_get(r, idx_hora_ing)
        hora_sal = safe_get(r, idx_hora_sal)
        tipo_trabajo = safe_get(r, idx_tipo)
        extension = safe_get(r, idx_ext)
        interventor = safe_get(r, idx_interv)
        turno = safe_get(r, idx_turno)
        fecha_inicio = safe_get(r, idx_fini)
        fecha_fin = safe_get(r, idx_ffin)

        key = "|".join([
            empresa, nit, hora_ing, hora_sal, tipo_trabajo,
            extension, interventor, turno, fecha_inicio, fecha_fin
        ])

        if key not in solicitudes:
            solicitudes[key] = {
                "empresa": empresa,
                "nit": nit,
                "horaIngreso": hora_ing,
                "horaSalida": hora_sal,
                "tipoTrabajo": tipo_trabajo,
                "extension": extension,
                "interventor": interventor,
                "turno": turno,
                "fechaInicio": fecha_inicio,
                "fechaFin": fecha_fin,
                "personas": []
            }

        induccion = safe_get(r, COL_IND)
        seguridadSocial = safe_get(r, COL_SS)

        motivos = []
        if induccion != "VIGENTE":
            motivos.append("Inducción")
        if seguridadSocial != "VIGENTE":
            motivos.append("Seguridad Social")

        solicitudes[key]["personas"].append({
            "row": sheet_row,
            "nombre": f"{safe_get(r, idx_nombre)} {safe_get(r, idx_apellido)}".strip(),
            "cedula": safe_get(r, idx_cedula),
            "induccion": induccion,
            "seguridadSocial": seguridadSocial,
            "estado": "CUMPLE" if not motivos else "REVISAR",
            "motivo": " · ".join(motivos),
            "consecutivo": safe_get(r, idx_consec)
        })

    return list(solicitudes.values())

def actualizar_consecutivo(row: int, consecutivo: str):
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID en .env")

    col_letter = "X"  # tu consecutivo
    range_a1 = f"{base_name}!{col_letter}{row}"
    write_sheet_value(base_id, range_a1, consecutivo)

def actualizar_consecutivos_batch(changes: list[dict]):
    """
    changes = [{"row": 12, "consecutivo": "3553"}, ...]
    Escribe en columna X (CONSECUTIVO) de Base_Personas en batch (rápido).
    """
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")
    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID en .env")

    svc = sheets_service()

    # columna del consecutivo
    col_letter = "X"

    data = []
    for c in changes:
        try:
            row = int(c["row"])
            consecutivo = str(c.get("consecutivo", "")).strip()
        except Exception:
            continue

        if not consecutivo:
            continue

        data.append({
            "range": f"{base_name}!{col_letter}{row}",
            "values": [[consecutivo]]
        })

    if not data:
        return

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=base_id,
        body={"valueInputOption": "USER_ENTERED", "data": data}
    ).execute()

