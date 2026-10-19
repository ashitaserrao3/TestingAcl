"""
Save changed data files to this repo on GitHub in one commit, so a tariff Ashita
uploads in the app stays after the app restarts and everyone sees it.
Streamlit Cloud redeploys the app from the new commit within about a minute.

Needs a [github] section in Streamlit Secrets (see secrets.toml.example).
"""

import base64
import os

import requests

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHub:
    def __init__(self, token, repo, branch="main", session=None):
        self.repo, self.branch = repo, branch
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})

    def _call(self, method, path, json=None):
        r = self.s.request(method, f"{API}/repos/{self.repo}/{path}", json=json, timeout=300)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub said {r.status_code}: {r.text[:200]}")
        return r.json()

    def commit(self, files, message):
        """files: {repo path: bytes to write, or None to delete}. Returns the new commit's id."""
        head = self._call("GET", f"git/ref/heads/{self.branch}")["object"]["sha"]
        base_tree = self._call("GET", f"git/commits/{head}")["tree"]["sha"]
        tree = []
        for path, data in sorted(files.items()):
            if data is None:
                tree.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue
            blob = self._call("POST", "git/blobs", {"content": base64.b64encode(data).decode(),
                                                     "encoding": "base64"})["sha"]
            tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob})
        new_tree = self._call("POST", "git/trees", {"base_tree": base_tree, "tree": tree})["sha"]
        new = self._call("POST", "git/commits", {"message": message, "tree": new_tree, "parents": [head]})["sha"]
        self._call("PATCH", f"git/refs/heads/{self.branch}", {"sha": new})
        return new
