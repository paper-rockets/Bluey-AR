#!/usr/bin/env python3
"""Static server for the CLAUDE app folder, plus a tiny command relay so a phone
on the same Wi-Fi can drive the Crew display.

    py remote_server.py [port]        # default 8937

Serves this folder exactly like `py -m http.server` did, and adds:

    GET  /api/info              -> {"lan": "192.168.x.x", "port": 8937}
    POST /api/cmd   {...}       -> queue a command from the phone
    GET  /api/cmd?since=N       -> {"seq": N, "cmds": [...]} for the display

The command log lives in memory only; there is no persistence and no auth, so
run it on a home network you trust. Binding is 0.0.0.0 because the phone has to
reach it (`py -m http.server` did the same).
"""

import json
import os
import socket
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_LOG = 200

_lock = threading.Lock()
_seq = 0
_log = []  # [(seq, cmd_dict)]


def lan_ip():
    """Best-guess LAN address. Opens a UDP socket to pick the default route --
    no packets are actually sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(SimpleHTTPRequestHandler):
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/cmd":
            since = (parse_qs(u.query).get("since") or ["0"])[0]
            try:
                since = int(since)
            except ValueError:
                since = 0
            with _lock:
                cmds = [c for s, c in _log if s > since]
                seq = _seq
            return self._json({"seq": seq, "cmds": cmds})
        if u.path == "/api/info":
            return self._json({"lan": lan_ip(), "port": self.server.server_address[1]})
        return super().do_GET()

    def do_POST(self):
        global _seq
        if urlparse(self.path).path != "/api/cmd":
            return self.send_error(404)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            cmd = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self.send_error(400, "bad json")
        if not isinstance(cmd, dict):
            return self.send_error(400, "command must be an object")
        with _lock:
            _seq += 1
            _log.append((_seq, cmd))
            del _log[:-MAX_LOG]
            seq = _seq
        self._json({"ok": True, "seq": seq})

    def log_message(self, *args):
        pass  # the display polls several times a second; don't flood the console


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8937
    srv = ThreadingHTTPServer(("0.0.0.0", port), partial(Handler, directory=ROOT))
    ip = lan_ip()
    print(f"serving {ROOT}")
    print(f"  display : http://localhost:{port}/Crew/crew.html")
    print(f"  remote  : http://{ip}:{port}/Crew/remote.html   (phone, same Wi-Fi)")
    print("ctrl-c to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
