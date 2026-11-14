"""Bounded ZIP inspection and durable GitHub intake; never extracts or executes uploads."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import stat
import urllib.error
import urllib.request
import zipfile
from pathlib import PurePosixPath

MAX_UPLOAD = 15 * 1024 * 1024
MAX_EXPANDED = 100 * 1024 * 1024
MAX_FILES = 2000
REPOSITORY = "bartimoussmith-oss/therealwindycity"


def inspect_bundle(data: bytes) -> dict:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("ZIP must be nonempty and no larger than 15 MiB.")
    files = []
    total = 0
    seen = set()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES:
                raise ValueError("ZIP contains more than 2,000 entries.")
            for entry in entries:
                name = entry.filename
                path = PurePosixPath(name)
                if (not name or path.is_absolute() or ".." in path.parts
                        or "\\" in name or ":" in name
                        or any(ord(c) < 32 for c in name)):
                    raise ValueError("ZIP contains an unsafe filename.")
                if path.as_posix() in seen:
                    raise ValueError("ZIP contains duplicate filenames.")
                seen.add(path.as_posix())
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError("ZIP contains links or special files.")
                if entry.flag_bits & 1:
                    raise ValueError("Encrypted ZIP files are not supported.")
                total += entry.file_size
                if total > MAX_EXPANDED:
                    raise ValueError("ZIP expands beyond the 100 MiB safety limit.")
                if not entry.is_dir():
                    # Stream every member to verify CRC and detect corrupt archives.
                    count = 0
                    with archive.open(entry) as source:
                        while chunk := source.read(65536):
                            count += len(chunk)
                            if count > entry.file_size or count > MAX_EXPANDED:
                                raise ValueError("ZIP member exceeds its declared size.")
                    files.append({"path": name, "bytes": entry.file_size})
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError) as exc:
        raise ValueError("ZIP is corrupt or uses an unsupported compression method.") from exc
    if not files:
        raise ValueError("ZIP contains no files.")
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
            "expanded_bytes": total, "files": files}


def publish_bundle(data: bytes, digest: str, token: str, branch: str) -> dict:
    """Create a content-addressed ZIP on the explicitly configured branch only."""
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Bundle checksum mismatch.")
    path = f"uploads/change-bundles/{digest}.zip"
    payload = json.dumps({"message": f"intake: change bundle {digest[:12]}",
                          "branch": branch,
                          "content": base64.b64encode(data).decode("ascii")}).encode()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/contents/{path}",
        data=payload, method="PUT", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        messages = {401: "GitHub authentication failed. Check the server secret.",
                    403: "GitHub denied access. Check repository Contents write permission and branch rules.",
                    404: "Repository or configured branch is unavailable to the server token.",
                    409: "GitHub reported a conflict. The bundle may already exist; check the intake folder.",
                    422: "GitHub rejected the upload. The bundle may already exist; check the intake folder."}
        raise ValueError(messages.get(exc.code, "GitHub could not save the bundle. Try again later.")) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("GitHub connection failed or timed out. Check the intake folder before retrying.") from None
    return {"path": path, "url": result["content"]["html_url"],
            "commit": result["commit"]["sha"]}
