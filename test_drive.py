from google_client import drive_service

FILE_ID = "1j3hzvUBDnN4wCc2RcmrsACSXoOzE5fcVBqK8O_2QlSM"  # cambia por uno tuyo

drive = drive_service()

meta = drive.files().get(
    fileId=FILE_ID,
    supportsAllDrives=True,
    fields="id,name,mimeType,owners,driveId"
).execute()

print("OK:", meta["name"], meta["mimeType"])
