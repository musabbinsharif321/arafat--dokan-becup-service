import os
import sys
import json
import gzip
import subprocess
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# Force unbuffered output so logs appear instantly on Railway
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# 1. Environment Variables Validation
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
SA_KEY_RAW = os.environ.get("GDRIVE_SA_KEY", "").strip()

# OAuth2 credentials (for personal Google Drive with 5 TB quota)
CLIENT_ID = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
REFRESH_TOKEN = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()

retention_str = os.environ.get("BACKUP_RETENTION_DAYS", "0").strip()
try:
    RETENTION_DAYS = int(retention_str) if retention_str else 0
except ValueError:
    RETENTION_DAYS = 0

missing_vars = []
if not DATABASE_URL:
    missing_vars.append("DATABASE_URL")
if not FOLDER_ID:
    missing_vars.append("GDRIVE_FOLDER_ID")

# Check if either OAuth or Service Account is provided
is_oauth = bool(CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN)
is_sa = bool(SA_KEY_RAW)

if not is_oauth and not is_sa:
    missing_vars.append("GDRIVE_REFRESH_TOKEN (or GDRIVE_SA_KEY)")

if missing_vars:
    print(f"Error: Missing required environment variable(s): {', '.join(missing_vars)}", file=sys.stderr, flush=True)
    sys.exit(1)

# 2. Prepare backup filename
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
backup_file = f"backup_{timestamp}.sql.gz"

try:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting database backup: {backup_file}...")

    # 3. Safe pg_dump execution (with automatic retry if database is starting up)
    import time
    pg_dump_cmd = [
        "pg_dump",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        DATABASE_URL
    ]

    max_retries = 3
    retry_delay = 10
    success = False

    for attempt in range(1, max_retries + 1):
        with gzip.open(backup_file, "wb", compresslevel=6) as gz_out:
            process = subprocess.run(
                pg_dump_cmd,
                stdout=gz_out,
                stderr=subprocess.PIPE,
                text=False,
                check=False
            )

        if process.returncode == 0:
            success = True
            break

        err_msg = process.stderr.decode("utf-8", errors="replace")
        if attempt < max_retries:
            print(f"pg_dump attempt {attempt} failed ({err_msg.strip()}). Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
        else:
            raise RuntimeError(f"pg_dump failed with exit code {process.returncode}:\n{err_msg}")

    file_size_mb = os.path.getsize(backup_file) / (1024 * 1024)
    print(f"Database dumped and compressed successfully ({file_size_mb:.2f} MB).")

    # 4. Google Drive Authentication & Upload
    print("Connecting to Google Drive API...")
    if is_oauth:
        print("Using OAuth 2.0 User Credentials (5 TB Personal Quota)...")
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            None,
            refresh_token=REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
    else:
        print("Using Service Account Credentials...")
        sa_info = json.loads(SA_KEY_RAW)
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
        fields="id, name, size",
        supportsAllDrives=True
    ).execute()

    print(f"Backup uploaded successfully! File ID: {uploaded_file.get('id')}")

    # 5. Optional Retention Cleanup (Deletes old backups if RETENTION_DAYS > 0)
    if RETENTION_DAYS > 0:
        print(f"Checking for backups older than {RETENTION_DAYS} days in Google Drive...")
        query = f"'{FOLDER_ID}' in parents and name contains 'backup_' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = results.get("files", [])

        now = datetime.now(timezone.utc)
        for f in files:
            created_time_str = f.get("createdTime")
            if created_time_str:
                created_time = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                age_days = (now - created_time).total_seconds() / 86400
                if age_days > RETENTION_DAYS:
                    service.files().delete(fileId=f["id"], supportsAllDrives=True).execute()
                    print(f"Deleted old backup: {f['name']} (Age: {int(age_days)} days)")

except Exception as ex:
    import traceback
    print(f"Backup failed: {ex}", file=sys.stderr, flush=True)
    traceback.print_exc()
    sys.exit(1)

finally:
    # 6. Cleanup local temporary backup file
    if os.path.exists(backup_file):
        os.remove(backup_file)
        print("Cleaned up local temporary backup file.")