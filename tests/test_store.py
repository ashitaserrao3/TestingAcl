"""store.py against an in-memory stand-in for GitHub's Git Data API."""

import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store import GitHubStore, local_files  # noqa: E402


class Resp:
    def __init__(self, status, body=None, content=b""):
        self.status_code, self._body, self.content = status, body, content
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeGitHub:
    """Just enough of the API: refs, commits, trees (flat, recursive listing) and blobs."""

    def __init__(self):
        self.headers, self.objects, self.refs, self.calls = {}, {}, {}, []

    def _put(self, kind, obj):
        sha = hashlib.sha1((kind + json.dumps(obj, sort_keys=True, default=repr)).encode()).hexdigest()
        self.objects[sha] = (kind, obj)
        return sha

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def request(self, method, url, json=None, headers=None, timeout=None):
        path = url.split("/repos/o/r/", 1)[1]
        self.calls.append((method, path))
        if method == "GET" and path.startswith("git/ref/heads/"):
            sha = self.refs.get(path.rsplit("/", 1)[1])
            return Resp(200, {"object": {"sha": sha}}) if sha else Resp(404, {})
        if method == "GET" and path.startswith("git/commits/"):
            return Resp(200, {"tree": {"sha": self.objects[path.rsplit("/", 1)[1]][1]["tree"]}})
        if method == "GET" and path.startswith("git/trees/"):
            entries = self.objects[path.split("/")[2].split("?")[0]][1]
            return Resp(200, {"tree": [dict(e, type="blob") for e in entries]})
        if method == "GET" and path.startswith("git/blobs/"):
            return Resp(200, content=self.objects[path.rsplit("/", 1)[1]][1])
        if method == "POST" and path == "git/blobs":
            data = base64.b64decode(json["content"])
            sha = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
            self.objects[sha] = ("blob", data)
            return Resp(201, {"sha": sha})
        if method == "POST" and path == "git/trees":
            return Resp(201, {"sha": self._put("tree", json["tree"])})
        if method == "POST" and path == "git/commits":
            return Resp(201, {"sha": self._put("commit", json)})
        if method in ("POST", "PATCH") and path.startswith("git/refs"):
            name = json["ref"].rsplit("/", 1)[1] if method == "POST" else path.rsplit("/", 1)[1]
            self.refs[name] = json["sha"]
            return Resp(200, {})
        return Resp(422, {"message": f"unexpected {method} {path}"})


def write(folder, rel, data):
    path = os.path.join(folder, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def read_all(folder):
    return {rel: open(p, "rb").read() for rel, p in local_files(folder).items()}


def test_upload_survives_restart_and_reupload_replaces(tmp_path):
    gh = FakeGitHub()
    store = GitHubStore("t", "o/r", session=gh)
    app = tmp_path / "app"
    write(app, "rates/IndiGo Eff. 01st Oct 2026.xlsx", b"indigo oct")
    write(app, "schedule/dgca/a.pdf", b"pdf a")
    assert store.push(app, "upload") is True
    assert "data" in gh.refs  # branch created on the first upload

    restarted = tmp_path / "restarted"  # empty disk after an app restart
    assert store.pull(restarted) == 2
    assert read_all(restarted) == read_all(app)

    # Re-upload: new IndiGo file replaces the old one; unchanged files aren't sent again
    os.remove(app / "rates" / "IndiGo Eff. 01st Oct 2026.xlsx")
    write(app, "rates/IndiGo Eff. 16th Oct 2026.xlsx", b"indigo 16 oct")
    gh.calls.clear()
    assert store.push(app, "upload") is True
    assert [c for c in gh.calls if c == ("POST", "git/blobs")] == [("POST", "git/blobs")]

    assert store.pull(restarted) == 1
    assert read_all(restarted) == read_all(app)  # the old IndiGo file is gone there too
    assert store.push(app, "upload") is False    # nothing changed, no empty commit
