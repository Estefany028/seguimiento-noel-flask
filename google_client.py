# google_client.py
import os
import httplib2
import google_auth_httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    # necesario para convertir PDF -> Google Doc (copy) y leer archivos:
    "https://www.googleapis.com/auth/drive",
    # leer el contenido del Google Doc convertido:
    "https://www.googleapis.com/auth/documents.readonly",
]

def _creds():
    path = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)

def _authed_http(creds):
    # SOLO si tu red rompe SSL:
    http = httplib2.Http(disable_ssl_certificate_validation=True)
    return google_auth_httplib2.AuthorizedHttp(creds, http=http)

def sheets_service():
    creds = _creds()
    return build("sheets", "v4", http=_authed_http(creds), cache_discovery=False)

def drive_service():
    creds = _creds()
    return build("drive", "v3", http=_authed_http(creds), cache_discovery=False)

def docs_service():
    creds = _creds()
    return build("docs", "v1", http=_authed_http(creds), cache_discovery=False)

