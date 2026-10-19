"""
Keeps the tariffs Ashita uploads in one file in her Google Drive, so they stay
after the app restarts until she uploads again, without storing them in GitHub.

The file is a zip of the app's data/rates folder. The app signs in as a Google
service account and overwrites a file Ashita owns and has shared with it
(service accounts can't own files in a personal Drive, but they can edit one).

Needs in Streamlit Secrets (see secrets.toml.example):
    [drive] file_id = "..."            the shared file's id, from its link
    [gcp_service_account] ...          the service account's JSON key
"""

import io
import os
import zipfile

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

API = os.environ.get("DRIVE_API_URL", "https://www.googleapis.com")
SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveStore:
    def __init__(self, service_account_info, file_id):
        self.file_id = file_id
        self.creds = service_account.Credentials.from_service_account_info(dict(service_account_info), scopes=SCOPES)

    def _headers(self):
        if not self.creds.valid:
            self.creds.refresh(Request())
        return {"Authorization": f"Bearer {self.creds.token}"}

    def _check(self, r, what):
        if r.status_code >= 400:
            raise RuntimeError(f"Google Drive {what}: {r.status_code} {r.text[:200]}")
        return r

    def download(self):
        """The stored files {relative path: bytes}, or {} while the file holds nothing saved by the app yet."""
        r = self._check(requests.get(f"{API}/drive/v3/files/{self.file_id}", params={"alt": "media"},
                                     headers=self._headers(), timeout=120), "download")
        try:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                return {name: z.read(name) for name in z.namelist() if not name.endswith("/")}
        except zipfile.BadZipFile:
            return {}  # still the placeholder Ashita created

    def upload(self, files):
        """Replace the stored files with {relative path: bytes}."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(files.items()):
                z.writestr(name, data)
        self._check(requests.patch(f"{API}/upload/drive/v3/files/{self.file_id}", params={"uploadType": "media"},
                                   headers={**self._headers(), "Content-Type": "application/zip"},
                                   data=buf.getvalue(), timeout=300), "upload")
