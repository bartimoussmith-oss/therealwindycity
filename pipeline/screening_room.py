#!/usr/bin/env python3
"""Screening room server - serves pipeline/renders with Range support."""
import http.server, re, socketserver, sys
from pathlib import Path

ROOT = (Path(__file__).resolve().parent / "renders").resolve()
PORT = 8000
EXT = {".mp4": "video/mp4", ".vtt": "text/vtt; charset=utf-8",
       ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8",
       ".srt": "text/plain; charset=utf-8"}

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        f = (ROOT / path.lstrip("/")).resolve()
        if not str(f).startswith(str(ROOT)) or not f.is_file() or ".." in path:
            self.send_error(404)
            return
        ctype = EXT.get(f.suffix, "application/octet-stream")
        size = f.stat().st_size
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if not m:
                self.send_error(416)
                return
            start = int(m.group(1) or 0)
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
            if start > end or start >= size:
                self.send_error(416)
                return
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            self._send(f, start, end - start + 1)
        else:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            self._send(f, 0, size)

    def _send(self, f, start, n):
        with open(f, "rb") as fh:
            fh.seek(start)
            while n > 0:
                chunk = fh.read(min(65536, n))
                if not chunk:
                    break
                self.wfile.write(chunk)
                n -= len(chunk)

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}", flush=True)

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

print(f"Screening room serving {ROOT} on 0.0.0.0:{PORT}", flush=True)
Server(("0.0.0.0", PORT), Handler).serve_forever()
