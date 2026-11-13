#!/usr/bin/env python3
"""Shared team challenge API and loopback-only administrative API."""
import hmac
import ipaddress
import json
import os
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("TEAM_API_CONFIG", ROOT / "tasks-private.json"))
DB = Path(os.environ.get("TEAM_API_DB", ROOT / "progress.sqlite3"))
ADMIN_TOKEN_FILE = Path(os.environ.get("TEAM_API_ADMIN_TOKEN_FILE", ROOT / "admin-token"))
HOST = os.environ.get("TEAM_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("TEAM_API_PORT", "8765"))
MAX_BODY, RATE_WINDOW, RATE_LIMIT = 65536, 60, 60
rate_lock = threading.Lock()
config_lock = threading.RLock()
requests_by_ip = {}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_config(cfg):
    tasks = cfg.get("tasks") if isinstance(cfg, dict) else None
    if not isinstance(tasks, list) or len(tasks) > 20:
        raise ValueError("tasks must be a list of at most 20 items")
    ids = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "input", "expected", "fragment"}:
            raise ValueError("each task requires exactly id, input, expected, fragment")
        task_id = task["id"]
        if not isinstance(task_id, str) or not task_id or len(task_id) > 64 or "/" in task_id or task_id in ids:
            raise ValueError("task IDs must be unique non-empty strings without slashes")
        if not isinstance(task["input"], dict) or not isinstance(task["expected"], dict):
            raise ValueError("input and expected must be JSON objects")
        if not isinstance(task["fragment"], str) or len(task["fragment"]) > 1000:
            raise ValueError("fragment must be a string of at most 1000 characters")
        canonical(task["input"])
        canonical(task["expected"])
        ids.add(task_id)
    for key in ("contest_url_prefix", "contest_url_suffix"):
        if not isinstance(cfg.get(key, ""), str):
            raise ValueError(key + " must be a string")
    return cfg


def get_config():
    with config_lock:
        return validate_config(json.loads(CONFIG.read_text(encoding="utf-8")))


def save_config(cfg):
    validate_config(cfg)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=CONFIG.name + ".", suffix=".tmp", dir=CONFIG.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(cfg, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, CONFIG)
        os.chmod(CONFIG, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def connect_db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    conn = connect_db()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS completed (task_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL)")
        conn.commit()
    finally:
        conn.close()


def completed_ids(cfg):
    conn = connect_db()
    try:
        found = {row[0] for row in conn.execute("SELECT task_id FROM completed")}
    finally:
        conn.close()
    return [task["id"] for task in cfg["tasks"] if task["id"] in found]


def final_url(cfg, done):
    by_id = {task["id"]: task for task in cfg["tasks"]}
    return cfg.get("contest_url_prefix", "") + "".join(by_id[task_id]["fragment"] for task_id in done) + cfg.get("contest_url_suffix", "")


def limited(ip):
    now = time.monotonic()
    with rate_lock:
        recent = [stamp for stamp in requests_by_ip.get(ip, []) if now - stamp < RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            requests_by_ip[ip] = recent
            return True
        recent.append(now)
        requests_by_ip[ip] = recent
        return False


class Handler(BaseHTTPRequestHandler):
    server_version, sys_version = "TeamChallengeAPI/1.1", ""

    def log_message(self, fmt, *args):
        print("%s %s %s" % (self.log_date_time_string(), self.client_address[0], fmt % args), flush=True)

    def reply(self, status, value):
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid Content-Length")
        if size < 1 or size > MAX_BODY:
            raise ValueError("body must be 1..65536 bytes")
        try:
            return json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("body must be valid UTF-8 JSON")

    def is_local_admin_request(self):
        try:
            remote = ipaddress.ip_address(self.client_address[0])
            bound = ipaddress.ip_address(HOST)
        except ValueError:
            return False
        return remote.is_loopback or (not bound.is_unspecified and remote == bound)

    def admin_authorized(self):
        if not self.is_local_admin_request():
            return False
        try:
            expected = ADMIN_TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        supplied = self.headers.get("X-Admin-Token", "")
        return bool(expected) and hmac.compare_digest(supplied, expected)

    def hidden(self):
        return self.reply(404, {"error": "not_found"})

    def admin_gate(self):
        return self.admin_authorized() or self.hidden()

    def reset_one(self, task_id):
        conn = connect_db()
        try:
            conn.execute("DELETE FROM completed WHERE task_id=?", (task_id,))
            conn.commit()
        finally:
            conn.close()

    def do_GET(self):
        if limited(self.client_address[0]):
            return self.reply(429, {"error": "rate_limited"})
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/_admin/"):
            if not self.admin_gate():
                return
            cfg = get_config()
            if path == "/_admin/status":
                done = completed_ids(cfg)
                return self.reply(200, {"task_count": len(cfg["tasks"]), "completed": done, "completed_count": len(done)})
            if path == "/_admin/tasks":
                return self.reply(200, {"tasks": cfg["tasks"]})
            return self.hidden()
        if path == "/health":
            return self.reply(200, {"status": "ok"})
        try:
            cfg = get_config()
        except Exception:
            return self.reply(503, {"error": "service_not_configured"})
        if path == "/api/tasks":
            return self.reply(200, {"tasks": [{"id": task["id"]} for task in cfg["tasks"]]})
        if path.startswith("/api/tasks/") and path.endswith("/input"):
            task_id = path[len("/api/tasks/"):-len("/input")].strip("/")
            task = next((item for item in cfg["tasks"] if item["id"] == task_id), None)
            if task is None:
                return self.reply(404, {"error": "unknown_task"})
            return self.reply(200, {"task_id": task_id, "input": task["input"]})
        if path == "/api/progress":
            done = completed_ids(cfg)
            result = {"completed": done, "completed_count": len(done), "total_count": len(cfg["tasks"])}
            if cfg["tasks"] and len(done) == len(cfg["tasks"]):
                result["contest_url"] = final_url(cfg, done)
            return self.reply(200, result)
        return self.hidden()

    def do_POST(self):
        if limited(self.client_address[0]):
            return self.reply(429, {"error": "rate_limited"})
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/_admin/"):
            if not self.admin_gate():
                return
            try:
                body = self.read_body()
            except ValueError as exc:
                return self.reply(400, {"error": "invalid_request", "detail": str(exc)})
            if path == "/_admin/tasks":
                if not isinstance(body, dict) or set(body) != {"id", "input", "expected", "fragment"}:
                    return self.reply(400, {"error": "schema"})
                with config_lock:
                    cfg = get_config()
                    if any(task["id"] == body.get("id") for task in cfg["tasks"]):
                        return self.reply(409, {"error": "task_exists"})
                    cfg["tasks"].append(body)
                    try:
                        save_config(cfg)
                    except (OSError, ValueError, TypeError) as exc:
                        return self.reply(400, {"error": "invalid_task", "detail": str(exc)})
                return self.reply(201, {"created": body["id"]})
            if path == "/_admin/progress/reset":
                if not isinstance(body, dict):
                    return self.reply(400, {"error": "schema"})
                if body == {"all": True}:
                    conn = connect_db()
                    try:
                        conn.execute("DELETE FROM completed")
                        conn.commit()
                    finally:
                        conn.close()
                    return self.reply(200, {"reset": "all"})
                if set(body) == {"task_id"} and isinstance(body["task_id"], str):
                    cfg = get_config()
                    if not any(task["id"] == body["task_id"] for task in cfg["tasks"]):
                        return self.reply(404, {"error": "unknown_task"})
                    self.reset_one(body["task_id"])
                    return self.reply(200, {"reset": body["task_id"]})
                return self.reply(400, {"error": "schema"})
            return self.hidden()
        if path != "/api/submit":
            return self.hidden()
        try:
            body = self.read_body()
        except ValueError as exc:
            return self.reply(400, {"error": "invalid_request", "detail": str(exc)})
        if not isinstance(body, dict) or set(body) != {"task_id", "answer"} or not isinstance(body["task_id"], str):
            return self.reply(400, {"error": "schema", "expected": {"task_id": "string", "answer": "any JSON value"}})
        try:
            cfg = get_config()
        except Exception:
            return self.reply(503, {"error": "service_not_configured"})
        task = next((item for item in cfg["tasks"] if item["id"] == body["task_id"]), None)
        if task is None:
            return self.reply(404, {"error": "unknown_task"})
        try:
            if canonical(body["answer"]) != canonical(task["expected"]):
                return self.reply(200, {"correct": False})
        except (TypeError, ValueError):
            return self.reply(400, {"error": "answer_not_json_value"})
        conn = connect_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            already = conn.execute("SELECT 1 FROM completed WHERE task_id=?", (task["id"],)).fetchone() is not None
            conn.execute("INSERT OR IGNORE INTO completed(task_id, completed_at) VALUES (?, ?)", (task["id"], datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()
        done = completed_ids(cfg)
        result = {"correct": True, "task_id": task["id"], "fragment": task["fragment"], "already_completed": already}
        if cfg["tasks"] and len(done) == len(cfg["tasks"]):
            result["contest_url"] = final_url(cfg, done)
        return self.reply(200, result)

    def do_PUT(self):
        if limited(self.client_address[0]):
            return self.reply(429, {"error": "rate_limited"})
        path = unquote(urlsplit(self.path).path)
        prefix = "/_admin/tasks/"
        if not path.startswith(prefix):
            return self.hidden()
        if not self.admin_gate():
            return
        task_id = path[len(prefix):].strip("/")
        try:
            body = self.read_body()
        except ValueError as exc:
            return self.reply(400, {"error": "invalid_request", "detail": str(exc)})
        if not task_id or not isinstance(body, dict) or set(body) != {"input", "expected", "fragment"}:
            return self.reply(400, {"error": "schema"})
        with config_lock:
            cfg = get_config()
            task = next((item for item in cfg["tasks"] if item["id"] == task_id), None)
            if task is None:
                return self.reply(404, {"error": "unknown_task"})
            task.update(body)
            try:
                save_config(cfg)
            except (OSError, ValueError, TypeError) as exc:
                return self.reply(400, {"error": "invalid_task", "detail": str(exc)})
            self.reset_one(task_id)
        return self.reply(200, {"updated": task_id, "progress_reset": True})

    def do_DELETE(self):
        if limited(self.client_address[0]):
            return self.reply(429, {"error": "rate_limited"})
        path = unquote(urlsplit(self.path).path)
        prefix = "/_admin/tasks/"
        if not path.startswith(prefix):
            return self.hidden()
        if not self.admin_gate():
            return
        task_id = path[len(prefix):].strip("/")
        if not task_id:
            return self.hidden()
        with config_lock:
            cfg = get_config()
            remaining = [task for task in cfg["tasks"] if task["id"] != task_id]
            if len(remaining) == len(cfg["tasks"]):
                return self.reply(404, {"error": "unknown_task"})
            cfg["tasks"] = remaining
            save_config(cfg)
            self.reset_one(task_id)
        return self.reply(200, {"deleted": task_id, "progress_removed": True})


def main():
    init_db()
    print("Team challenge API listening on %s:%s" % (HOST, PORT), flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
