import os
from datetime import datetime, date
from google_client import sheets_service


# ===============================
# UTILIDADES
# ===============================

def _hoy_date():
    return date.today()


def _parse_sheet_date(v):

    if not v:
        return None

    s = str(v).strip()

    if " " in s:
        s = s.split(" ")[0]

    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except:
        pass

    try:
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d))
    except:
        pass

    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except:
        pass

    return None


# ===============================
# GOOGLE SHEETS
# ===============================

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


# ===============================
# BUSCAR INDICE DE COLUMNA
# ===============================

def _find_col(headers, text):

    text = text.upper()

    for i, h in enumerate(headers):

        if text in str(h).upper():
            return i

    return -1


# ===============================
# TABLERO EXTERNO
# ===============================

def obtener_personas_vigentes_externo():

    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    values = read_sheet_values(base_id, f"{base_name}!A1:AE")

    if not values:
        return []

    headers = values[0]
    rows = values[1:]

    def find_col(text):
        for i, h in enumerate(headers):
            if text in str(h).upper():
                return i
        return -1

    idx_nombre = find_col("NOMBRES")
    idx_apellido = find_col("APELLIDOS")
    idx_empresa = headers.index("EMPRESA") if "EMPRESA" in headers else -1
    idx_cedula = find_col("CEDULA")

    idx_ind = find_col("INDUCCIÓN")
    idx_ss = find_col("VIGENCIA SS")
    idx_leido = find_col("LEIDO")

    idx_fini = find_col("FECHA DE INICIO")
    idx_ffin = find_col("FECHA FIN")
     
    if idx_leido == -1:
        print("ERROR: No se encontró la columna LEIDO")

    out = []

    personas_dict = {}

    # PRIMER LOOP → guardar último registro
    for r in rows:

        if idx_cedula >= len(r):
            continue

        ced = str(r[idx_cedula]).strip()

        if not ced:
            continue

        personas_dict[ced] = r


    # SEGUNDO LOOP → procesar personas
    for r in personas_dict.values():

        nombre = ""
        if idx_nombre < len(r):
            nombre += str(r[idx_nombre])

        if idx_apellido < len(r):
            nombre += " " + str(r[idx_apellido])

        empresa = r[idx_empresa] if idx_empresa < len(r) else ""
        induccion = r[idx_ind] if idx_ind < len(r) else ""
        seguridad = r[idx_ss] if idx_ss < len(r) else ""
        leido = r[idx_leido] if idx_leido < len(r) else ""

        hoy = _hoy_date()

        fecha_inicio = None
        fecha_fin = None

        if idx_fini < len(r):
            fecha_inicio = _parse_sheet_date(r[idx_fini])

        if idx_ffin < len(r):
            fecha_fin = _parse_sheet_date(r[idx_ffin])

        # mostrar solo personas activas hoy
        if fecha_fin is None:
            continue

        if fecha_fin < hoy:
            continue

        motivos = []

        # =========================
        # SEGURIDAD SOCIAL
        # =========================

        seguridad_val = str(seguridad).upper().strip()

        if seguridad_val == "REVISAR":

            motivos.append(
                "La Seguridad Social no se pudo verificar.<br><br>"
                "Infórmalo a aprendizrelacionesydllo@noel.com.co, "
                "admmto@noel.com.co y melara@noel.com.co."
            )

        elif seguridad_val == "VENCIDA":

            motivos.append(
                "❌ Seguridad Social vencida"
            )

        # =========================
        # INDUCCIÓN
        # =========================

        if induccion == "SIN REGISTRO":

            motivos.append(
                "La Inducción no se pudo verificar.<br><br>"
                "Infórmalo a aprendizrelacionesydllo@noel.com.co, "
                "admmto@noel.com.co y melara@noel.com.co."
            )

        elif induccion == "VENCIDA":

            motivos.append(
                "❌ Inducción vencida<br><br>"
                '<a href="LINK_FORM_INDUCCION" target="_blank">Actualizar documentos</a>'
            )

        estado = "CUMPLE"

        seguridad_val = str(seguridad).upper().strip()
        induccion_val = str(induccion).upper().strip()

        if seguridad_val == "VENCIDA" or induccion_val == "VENCIDA":
            estado = "BLOQUEADO"

        elif motivos:
            estado = "REVISAR"

        print("DEBUG MOTIVO:", "<hr>".join(motivos))

        seguridad_val = str(seguridad).upper().strip()
        induccion_val = str(induccion).upper().strip()

        estado = "CUMPLE"

        # BLOQUEADO si algo está vencido
        if seguridad_val == "VENCIDA" or induccion_val == "VENCIDA":
            estado = "BLOQUEADO"

        # REVISAR si algo no se pudo leer
        elif seguridad_val == "REVISAR" or induccion_val == "SIN REGISTRO":
            estado = "REVISAR"

        out.append({
            "nombre": nombre.strip(),
            "cedula": ced,
            "empresa": empresa,
            "induccion": induccion,
            "seguridadSocial": seguridad,
            "estado": estado,
            "motivo": "<hr>".join(motivos)
        })

    return out


# ===============================
# ADMIN
# ===============================

def obtener_solicitudes_admin():

    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    values = read_sheet_values(base_id, f"{base_name}!A1:AE")
    
    print("DEBUG VALUES:", values[:3])

    if not values:
        return []

    headers = values[0]
    rows = values[1:]

    idx_empresa = headers.index("EMPRESA") if "EMPRESA" in headers else -1
    idx_nit = _find_col(headers, "NIT")

    idx_hora_ing = _find_col(headers, "HORA INGRESO")
    idx_hora_sal = _find_col(headers, "HORA SALIDA")

    idx_tipo = _find_col(headers, "TIPO DE INGRESO")
    idx_ext = _find_col(headers, "EXTENSION")
    idx_interv = _find_col(headers, "INTERVENTOR")
    idx_turno = _find_col(headers, "TURNO")

    idx_fini = _find_col(headers, "FECHA DE INICIO")
    idx_ffin = _find_col(headers, "FECHA FIN")

    idx_nombre = _find_col(headers, "NOMBRES")
    idx_apellido = _find_col(headers, "APELLIDOS")
    idx_cedula = _find_col(headers, "CEDULA")

    idx_ind = _find_col(headers, "INDUCCIÓN")
    idx_ss = _find_col(headers, "VIGENCIA SS")
    idx_leido = _find_col(headers, "LEIDO")

    idx_consec = _find_col(headers, "CONSECUTIVO")

    hoy = _hoy_date()

    solicitudes = {}

    for sheet_row, r in enumerate(rows, start=2):

        if idx_cedula >= len(r):
            continue

        ced = str(r[idx_cedula]).strip()

        if not ced:
            continue

        fin = None

        if idx_ffin < len(r):
            fin = _parse_sheet_date(r[idx_ffin])

        # ===============================
        # VALIDAR VENCIMIENTO SEGURIDAD SOCIAL
        # ===============================

        fecha_ss = None
        if idx_ss < len(r):
            fecha_ss = _parse_sheet_date(r[idx_ss])

        # si existe fecha de seguridad social
        if fecha_ss:

            # si la seguridad social vence antes que la solicitud
            if fin and fecha_ss < fin:

                # limitar la solicitud hasta la fecha de SS
                fin = fecha_ss

        if not fin or fin < hoy:
            continue

        empresa = r[idx_empresa] if idx_empresa < len(r) else ""

        key = empresa + str(fin)

        if key not in solicitudes:

            solicitudes[key] = {
                "empresa": empresa,
                "nit": r[idx_nit] if idx_nit < len(r) else "",
                "horaIngreso": r[idx_hora_ing] if idx_hora_ing < len(r) else "",
                "horaSalida": r[idx_hora_sal] if idx_hora_sal < len(r) else "",
                "fechaInicio": r[idx_fini] if idx_fini < len(r) else "",
                "fechaFin": str(fin),
                "interventor": r[idx_interv] if idx_interv < len(r) else "",
                "turno": r[idx_turno] if idx_turno < len(r) else "",
                "personas": []
            }

        induccion = r[idx_ind] if idx_ind < len(r) else ""
        seguridad = r[idx_ss] if idx_ss < len(r) else ""
        fecha_ss = _parse_sheet_date(seguridad)
        leido = r[idx_leido] if idx_leido < len(r) else ""

        fecha_ss = _parse_sheet_date(seguridad)

        semaforo_ss = "ok"

        if fecha_ss:
            
            if fecha_ss < hoy:
                semaforo_ss = "vencida"

            elif fin and fecha_ss < fin:
                semaforo_ss = "vence_durante"

        motivos = []

        seguridad_val = str(seguridad).upper().strip()
        leido_val = str(leido).upper().strip()

        # inducción
        if induccion == "SIN REGISTRO":
            motivos.append("Inducción no verificada")

        elif induccion == "VENCIDA":
            motivos.append("Inducción vencida")

        # seguridad social
        if leido_val != "OK":
            motivos.append("Seguridad Social no verificada")

        elif seguridad_val == "VENCIDA":
            motivos.append("Seguridad Social vencida")

        solicitudes[key]["personas"].append({

            "row": sheet_row,
            "nombre": f"{r[idx_nombre]} {r[idx_apellido]}",
            "cedula": ced,
            "induccion": induccion,
            "seguridadSocial": seguridad,
            "estado": "CUMPLE" if not motivos else "REVISAR",
            "motivo": " · ".join(motivos),
            "consecutivo": r[idx_consec] if idx_consec < len(r) else "",
            "ssSemaforo": semaforo_ss

        })

    return list(solicitudes.values())


# ===============================
# ACTUALIZAR CONSECUTIVO
# ===============================

def actualizar_consecutivo(row: int, consecutivo: str):

    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    col_letter = "X"

    write_sheet_value(
        base_id,
        f"{base_name}!{col_letter}{row}",
        consecutivo
    )

# ===============================
# ACTUALIZAR MUCHOS CONSECUTIVOS
# ===============================

def actualizar_consecutivos_batch(changes):

    base_id = os.getenv("SPREADSHEET_BASE_ID")
    base_name = os.getenv("SHEET_BASE_NAME", "Base_Personas")

    col_letter = "X"   # columna de consecutivo

    for c in changes:

        row = int(c["row"])
        consecutivo = str(c["consecutivo"]).strip()

        write_sheet_value(
            base_id,
            f"{base_name}!{col_letter}{row}",
            consecutivo
        )
