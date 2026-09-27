import os
import sys
import json
import gzip
import subprocess
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# 1. Environment Variables Validation
DATABASE_URL = os.environ.get("DATABASE_URL")
FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")
SA_KEY_RAW = os.environ.get("GDRIVE_SA_KEY")
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "0"))  # 0 means disabled

missing_vars = []
if not DATABASE_URL:
    missing_vars.append("DATABASE_URL")
if not FOLDER_ID:
    missing_vars.append("GDRIVE_FOLDER_ID")
if not SA_KEY_RAW:
    missing_vars.append("GDRIVE_SA_KEY")

if missing_vars:
    print(f"Error: Missing required environment variable(s): {', '.join(missing_vars)}", file=sys.stderr)
    sys.exit(1)

# Parse Service Account Key directly from memory
try:
    sa_info = json.loads(SA_KEY_RAW)
except json.JSONDecodeError as e:
    print(f"Error parsing GDRIVE_SA_KEY JSON: {e}", file=sys.stderr)
    sys.exit(1)

# 2. Prepare backup filename
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
backup_file = f"backup_{timestamp}.sql.gz"

try:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting database backup: {backup_file}...")

    # 3. Safe pg_dump execution (without shell=True, streaming directly into gzip)
    # Using --no-owner --no-acl ensures smooth restore on any target PostgreSQL
    pg_dump_cmd = [
        "pg_dump",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        DATABASE_URL
    ]

    with gzip.open(backup_file, "wb", compresslevel=6) as gz_out:
        process = subprocess.run(
            pg_dump_cmd,
            stdout=gz_out,
            stderr=subprocess.PIPE,
            text=False,
            check=False
        )

    if process.returncode != 0:
        err_msg = process.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"pg_dump failed with exit code {process.returncode}:\n{err_msg}")

    file_size_mb = os.path.getsize(backup_file) / (1024 * 1024)
    print(f"Database dumped and compressed successfully ({file_size_mb:.2f} MB).")

    # 4. Google Drive Authentication & Upload
    print("Connecting to Google Drive API...")
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)

    print(f"Uploading {backup_file} to Google Drive folder '{FOLDER_ID}'...")
    file_metadata = {
        "name": backup_file,
        "parents": [FOLDER_ID]
    }
    media = MediaFileUpload(backup_file, mimetype="application/gzip", resumable=True)
    uploaded_file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, size"
    ).execute()

    print(f"Backup uploaded successfully! File ID: {uploaded_file.get('id')}")

    # 5. Optional Retention Cleanup (Deletes old backups if RETENTION_DAYS > 0)
    if RETENTION_DAYS > 0:
        print(f"Checking for backups older than {RETENTION_DAYS} days in Google Drive...")
        query = f"'{FOLDER_ID}' in parents and name contains 'backup_' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc"
        ).execute()
        files = results.get("files", [])

        now = datetime.now(timezone.utc)
        for f in files:
            created_time_str = f.get("createdTime")
            if created_time_str:
                created_time = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                age_days = (now - created_time).total_seconds() / 86400
                if age_days > RETENTION_DAYS:
                    service.files().delete(fileId=f["id"]).execute()
                    print(f"Deleted old backup: {f['name']} (Age: {int(age_days)} days)")

except Exception as ex:
    print(f"Backup failed: {ex}", file=sys.stderr)
    sys.exit(1)

finally:
    # 6. Cleanup local temporary backup file
    if os.path.exists(backup_file):
        os.remove(backup_file)
        print("Cleaned up local temporary backup file.")