"""
Keeps the uploaded schedule and tariff files on a branch of this GitHub repo
(default `data`), so the Flight Schedule keeps showing them after the app
restarts, until Ashita uploads new files.

    push(folder)  makes the branch hold exactly the files in `folder` (one commit)
    pull(folder)  makes `folder` hold exactly the files on the branch

Uses GitHub's Git Data API, so each upload is a single commit and files up to
100 MB work. Pushing to a branch other than the one Streamlit deploys from
does not restart the app.
"""

import base64
import hashlib
import os

import requests

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


def blob_sha(path):
    """The id git gives a file's contents - lets push/pull skip files that haven't changed."""
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def local_files(folder):
    """{'rates/x.xlsx': '/abs/path', ...} for every file under `folder`."""
    out = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            out[os.path.relpath(path, folder).replace(os.sep, "/")] = path
    return out


class GitHubStore:
    def __init__(self, token, repo, branch="data", session=None):
        self.repo, self.branch = repo, branch
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})

    def _url(self, path):
        return f"{API}/repos/{self.repo}/{path}"

    def _call(self, method, path, json=None, headers=None):
        r = self.s.request(method, self._url(path), json=json, headers=headers, timeout=300)
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub {method} {path}: {r.status_code} {r.text[:200]}")
        return r

    def head(self):
        """The branch's latest commit, or None when the branch doesn't exist yet."""
        r = self.s.get(self._url(f"git/ref/heads/{self.branch}"), timeout=60)
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"GitHub GET branch {self.branch}: {r.status_code} {r.text[:200]}")
        return r.json()["object"]["sha"]

    def remote_files(self, commit):
        """{path: blob sha} for every file in `commit`."""
        tree = self._call("GET", f"git/commits/{commit}").json()["tree"]["sha"]
        listing = self._call("GET", f"git/trees/{tree}?recursive=1").json()
        return {e["path"]: e["sha"] for e in listing["tree"] if e["type"] == "blob"}

    def pull(self, folder):
        """Make `folder` match the branch. Returns the number of files downloaded."""
        commit = self.head()
        if not commit:
            return 0
        remote = self.remote_files(commit)
        for rel, path in local_files(folder).items():
            if rel not in remote:
                os.remove(path)
        n = 0
        for rel, sha in remote.items():
            dest = os.path.join(folder, *rel.split("/"))
            if os.path.isfile(dest) and blob_sha(dest) == sha:
                continue
            data = self._call("GET", f"git/blobs/{sha}", headers={"Accept": "application/vnd.github.raw+json"}).content
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
            n += 1
        return n

    def push(self, folder, message):
        """Make the branch match `folder` in one commit. Returns False when nothing changed."""
        commit = self.head()
        remote = self.remote_files(commit) if commit else {}
        tree = []
        for rel, path in sorted(local_files(folder).items()):
            sha = blob_sha(path)
            if remote.get(rel) != sha:
                with open(path, "rb") as f:
                    content = base64.b64encode(f.read()).decode()
                sha = self._call("POST", "git/blobs", {"content": content, "encoding": "base64"}).json()["sha"]
            tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": sha})
        if {t["path"]: t["sha"] for t in tree} == remote and (commit or not tree):
            return False
        tree_sha = self._call("POST", "git/trees", {"tree": tree}).json()["sha"]
        new = self._call("POST", "git/commits", {"message": message, "tree": tree_sha,
                                                 "parents": [commit] if commit else []}).json()["sha"]
        if commit:
            self._call("PATCH", f"git/refs/heads/{self.branch}", {"sha": new})
        else:
            self._call("POST", "git/refs", {"ref": f"refs/heads/{self.branch}", "sha": new})
        return True
