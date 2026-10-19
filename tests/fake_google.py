"""A stand-in for Google's token endpoint and the Drive file download / upload, for tests."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


class FakeGoogle:
    def __init__(self, port=0, content=b"placeholder"):
        self.files = {"FILE1": content}
        self.uploads = 0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code, body, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(body if isinstance(body, bytes) else json.dumps(body).encode())

            def _authorised(self):
                return self.headers.get("Authorization") == "Bearer fake-token"

            def do_POST(self):  # token exchange
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self._send(200, {"access_token": "fake-token", "expires_in": 3600, "token_type": "Bearer"})

            def do_GET(self):
                fid = self.path.split("/files/", 1)[-1].split("?")[0]
                if not self._authorised() or fid not in fake.files:
                    return self._send(404, {"error": "not found"})
                self._send(200, fake.files[fid], "application/octet-stream")

            def do_PATCH(self):
                fid = self.path.split("/files/", 1)[-1].split("?")[0]
                data = self.rfile.read(int(self.headers["Content-Length"]))
                if not self._authorised() or fid not in fake.files:
                    return self._send(404, {"error": "not found"})
                fake.files[fid] = data
                fake.uploads += 1
                self._send(200, {"id": fid})

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def service_account(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
        return {"type": "service_account", "project_id": "test", "private_key_id": "k1", "private_key": pem,
                "client_email": "app@test.iam.gserviceaccount.com", "client_id": "1",
                "token_uri": f"{self.url}/token"}

    def close(self):
        self.server.shutdown()


if __name__ == "__main__":  # run it on a fixed port, e.g. to try the app by hand
    import sys
    g = FakeGoogle(port=int(sys.argv[1]))
    with open(sys.argv[2], "w") as f:
        json.dump(g.service_account(), f)
    threading.Event().wait()
