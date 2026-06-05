#!/usr/bin/env python3
"""kuma-feed — read-only JSON feed of Uptime Kuma monitors, tags, and latest status.

Reads the Uptime Kuma SQLite DB directly (named volume mounted at /data).
The connection is opened normally (so SQLite can attach to the WAL shared-memory
index of the live DB) but PRAGMA query_only=1 guarantees we never write data.

Endpoint:
  GET /monitors  -> {"monitors":[{id,name,type,status,tags:[{name,value}]}], "ts": "..."}
    status: 1 = up, 0 = down, 2 = pending, 3 = maintenance, null = no heartbeat yet
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB_PATH = os.environ.get("KUMA_DB", "/data/kuma.db")
PORT = int(os.environ.get("PORT", "3099"))


def query_monitors():
    con = sqlite3.connect(DB_PATH, timeout=5)
    try:
        con.execute("PRAGMA query_only=1")
        con.execute("PRAGMA busy_timeout=4000")
        cur = con.cursor()

        # Active, non-group monitors
        cur.execute("SELECT id, name, type FROM monitor WHERE active=1 AND type != 'group'")
        mons = {
            r[0]: {"id": r[0], "name": r[1], "type": r[2], "status": None, "tags": []}
            for r in cur.fetchall()
        }

        # Tags (with per-monitor value)
        cur.execute(
            "SELECT mt.monitor_id, t.name, mt.value "
            "FROM monitor_tag mt JOIN tag t ON t.id = mt.tag_id"
        )
        for mid, tname, tval in cur.fetchall():
            if mid in mons:
                mons[mid]["tags"].append({"name": tname, "value": tval})

        # Latest heartbeat status per monitor
        cur.execute(
            "SELECT h.monitor_id, h.status FROM heartbeat h "
            "JOIN (SELECT monitor_id, MAX(time) mt FROM heartbeat GROUP BY monitor_id) l "
            "ON h.monitor_id = l.monitor_id AND h.time = l.mt"
        )
        for mid, status in cur.fetchall():
            if mid in mons:
                mons[mid]["status"] = status

        return list(mons.values())
    finally:
        con.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/monitors":
            self.send_response(404)
            self.end_headers()
            return
        try:
            payload = {
                "monitors": query_monitors(),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:  # noqa: BLE001
            body = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *_args):
        pass  # quiet


if __name__ == "__main__":
    print(f"kuma-feed listening on :{PORT}, db={DB_PATH}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
