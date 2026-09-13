"""
engine/local_store.py — Local server copy + external link preservation

Guarantees:
- Every document saved has BOTH external_url (original) and local_path (server copy)
- If external site down, serve from local_path
- RAG vector DB stored on server (server_data/<city>/vectordb/) + backup to R2
- No dependency on external sites for reading

Layout:
  server_data/
    cheyenne/
      meetings/1103/
        agenda.html (local copy, external_url = https://cheyenne.granicus.com/AgendaViewer.php?...)
        agenda.txt (extracted text)
        minutes.pdf + minutes.txt + external_url
        docs/staff_report.pdf + external_url MetaViewer
        video/meeting.mp4 + external_url archive-video
        captions.vtt + external_url YouTube
        manifest.json {files: [{name, external_url, local_path, sha256, size, fetched_at}]}
      boards/
      code/
      law/
      vectordb/
        chroma.sqlite3
        chunks.jsonl
      wayback/

Usage:
  from engine.local_store import LocalStore
  store = LocalStore(city="cheyenne", root="server_data")
  store.save_document(url="https://...", data=bytes, meeting_id="1103", kind="minutes")
  local_path = store.get_local_path("https://...")
  data = store.read_local("https://...")  # serves from local even if external down
"""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from datetime import datetime

class LocalStore:
    def __init__(self, city="cheyenne", root="server_data"):
        self.city = city
        self.root = Path(root) / city
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.manifest = self._load_manifest()

    def _load_manifest(self):
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"city": self.city, "generated_at": "", "files": {}, "external_map": {}}

    def _save_manifest(self):
        self.manifest["generated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1), encoding="utf-8")

    def _sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def save_document(self, url: str, data: bytes, meeting_id: str = None, kind: str = "doc", filename: str = None):
        """
        Save external URL content to local server copy.
        Preserves external_url + local_path + sha256.
        """
        import re
        if not filename:
            # guess from URL
            base = url.split("/")[-1].split("?")[0] or "doc.pdf"
            filename = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120] or "doc.pdf"
        # determine subfolder
        if meeting_id:
            sub = self.root / "meetings" / str(meeting_id) / kind
        else:
            sub = self.root / kind
        sub.mkdir(parents=True, exist_ok=True)
        local_path = sub / filename
        local_path.write_bytes(data)
        sha = self._sha256(data)
        # update manifest
        key = url
        self.manifest["files"][key] = {
            "external_url": url,
            "local_path": str(local_path),
            "filename": filename,
            "meeting_id": meeting_id,
            "kind": kind,
            "sha256": sha,
            "size": len(data),
            "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.manifest["external_map"][str(local_path)] = url
        self._save_manifest()
        return str(local_path), sha

    def get_local_path(self, url: str):
        entry = self.manifest["files"].get(url)
        if entry:
            return entry["local_path"]
        return None

    def has_local_copy(self, url: str) -> bool:
        p = self.get_local_path(url)
        return bool(p and Path(p).exists())

    def read_local(self, url: str) -> bytes | None:
        p = self.get_local_path(url)
        if p and Path(p).exists():
            return Path(p).read_bytes()
        return None

    def save_text(self, url: str, text: str, meeting_id: str = None, kind: str = "doc"):
        data = text.encode("utf-8")
        return self.save_document(url, data, meeting_id, kind, filename=kind+".txt")

    def list_meeting(self, meeting_id: str):
        folder = self.root / "meetings" / str(meeting_id)
        if not folder.exists():
            return []
        return [str(p.relative_to(self.root)) for p in folder.rglob("*") if p.is_file()]

    def verify_no_dependency(self):
        """
        Verify that every external_url has a local copy.
        Returns (ok, missing)
        """
        missing = []
        for url, info in self.manifest["files"].items():
            lp = info.get("local_path")
            if not lp or not Path(lp).exists():
                missing.append(url)
        return (len(missing)==0, missing)

# Example for RAG vectordb storage on server
class VectorStoreLocal:
    def __init__(self, city="cheyenne", root="server_data"):
        self.city = city
        self.root = Path(root) / city / "vectordb"
        self.root.mkdir(parents=True, exist_ok=True)

    def persist_path(self):
        return str(self.root)

    def chunks_path(self):
        return str(self.root / "chunks.jsonl")

    def save_chunks(self, chunks):
        # chunks: list of {id, text, metadata}
        with open(self.chunks_path(), "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c)+"\n")

    def backup_to_r2_instructions(self):
        return {
            "r2_bucket": "therealwindycity",
            "r2_prefix": f"cities/{self.city}/vectordb/",
            "local_path": self.persist_path(),
            "sync_cmd": f"wrangler r2 object put therealwindycity/cities/{self.city}/vectordb/chroma.sqlite3 --file={self.root}/chroma.sqlite3",
            "note": "R2 egress always free, local is primary, R2 is backup. No external dependency for reading."
        }
