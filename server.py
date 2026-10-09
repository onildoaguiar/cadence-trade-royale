"""Serve the pit. The brains run in-process; the page only watches and flips the feed.

    python server.py
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from attention_royale.live_feed import LiveFeed
from attention_royale.match import League

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
TICK = 0.09

os.environ.setdefault("OMP_NUM_THREADS", "1")


class Pit:
    def __init__(self, nursery_moments: int, feed: LiveFeed | None = None) -> None:
        self.lock = threading.Lock()
        self.league = League(nursery_moments=nursery_moments, feed=feed or LiveFeed())
        self.running = False
        self.error: str | None = None
        self._stop = False

    def boot(self) -> None:
        try:
            def on_progress(progress: dict) -> None:
                with self.lock:
                    self.league.progress = progress

            self.league.raise_all(on_progress)
            with self.lock:
                self.running = True
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"

    def loop(self) -> None:
        while not self._stop:
            began = time.perf_counter()
            with self.lock:
                if self.running and self.league.phase == "live":
                    self.league.step()
            remaining = TICK - (time.perf_counter() - began)
            if remaining > 0:
                time.sleep(remaining)

    def state(self) -> dict:
        with self.lock:
            payload = self.league.snapshot()
            payload["running"] = self.running
            payload["error"] = self.error
            return payload

    def command(self, cmd: str) -> dict:
        with self.lock:
            if self.league.phase != "live":
                return self.league.snapshot() | {"running": self.running, "error": self.error}
            if cmd == "play":
                self.running = True
            elif cmd == "pause":
                self.running = False
            elif cmd == "flip":
                self.league.flip()
            elif cmd == "round":
                self.league.new_round()
            elif cmd == "toggle":
                self.running = not self.running
            payload = self.league.snapshot()
            payload["running"] = self.running
            payload["error"] = self.error
            return payload


class Handler(BaseHTTPRequestHandler):
    pit: Pit

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(self.pit.state())
            return
        if path == "/":
            path = "/index.html"
        file_path = (WEB / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(WEB.resolve())) or not file_path.is_file():
            self.send_error(404)
            return
        kind = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/command":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json({"error": "bad json"}, 400)
            return
        self._json(self.pit.command(str(payload.get("cmd", ""))))

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Trending Royale")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--moments", type=int, default=360)
    args = parser.parse_args()
    pit = Pit(args.moments)
    Handler.pit = pit
    threading.Thread(target=pit.boot, daemon=True).start()
    threading.Thread(target=pit.loop, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Trending Royale  http://{args.host}:{args.port}/", flush=True)
    print("Reading crypto news, then raising six brains. The page shows that while it runs.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        pit._stop = True
        server.server_close()


if __name__ == "__main__":
    main()
