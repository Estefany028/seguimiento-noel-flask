# worker.py
import os
import time
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from google_client import sheets_service
from pipeline import procesar_xlsx_link_y_validar, parse_ts_form

def _set_procesado(svc, base_id: str, form_name: str, row_idx: int, value: str):
    try:
        svc.spreadsheets().values().update(
            spreadsheetId=base_id,
            range=f"{form_name}!D{row_idx}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]}
        ).execute()
    except Exception as e:
        print(f"⚠️ No pude escribir en D{row_idx}: {e}")

def poll_once():
    base_id = os.getenv("SPREADSHEET_BASE_ID")
    form_name = os.getenv("SHEET_FORM_NAME", "Respuestas de formulario 1")
    if not base_id:
        raise RuntimeError("Falta SPREADSHEET_BASE_ID")

    svc = sheets_service()

    values = svc.spreadsheets().values().get(
        spreadsheetId=base_id,
        range=f"{form_name}!A2:D",
        valueRenderOption="FORMATTED_VALUE"
    ).execute().get("values", [])

    nuevos = []
    for i, r in enumerate(values, start=2):
        if len(r) < 3:
            continue
        ts = r[0]
        link = r[2]
        procesado = (r[3].strip().upper() if len(r) >= 4 and r[3] else "")

        if procesado == "SI":
            continue

        dt = parse_ts_form(ts)
        if not dt or not link:
            continue

        nuevos.append((dt, i, ts, link))

    nuevos.sort(key=lambda x: x[0])

    for dt, row_idx, ts, link in nuevos:
        print(f"[{datetime.now().isoformat()}] Procesando fila {row_idx}: {ts} -> {link}")
        try:
            procesar_xlsx_link_y_validar(link)
            _set_procesado(svc, base_id, form_name, row_idx, "SI")
        except Exception as e:
            msg = str(e).replace("\n", " ")[:200]
            print("ERROR procesando submit:", ts, e)
            _set_procesado(svc, base_id, form_name, row_idx, f"ERROR: {msg}")

    return len(nuevos)

def main():
    poll_seconds = int(os.getenv("POLL_SECONDS", "45"))
    print("Worker iniciado. Poll cada", poll_seconds, "segundos.")
    while True:
        try:
            n = poll_once()
            if n:
                print("Nuevos encontrados:", n)
        except Exception as e:
            print("ERROR en poll:", e)
        time.sleep(poll_seconds)

if __name__ == "__main__":
    main()
