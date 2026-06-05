#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socketserver
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parent
ROOMS_FILE = DATA_DIR / "rooms.json"
USERS_FILE = DATA_DIR / "users.json"
MAX_MESSAGES = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_secret(value: str, hashed: str) -> bool:
    return hash_secret(value) == hashed


class ChatState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.rooms: Dict[str, Dict[str, Any]] = {}
        self.users: Dict[str, Dict[str, Any]] = {}
        self.active_user_counts: Dict[str, int] = {}
        self.room_user_counts: Dict[str, Dict[str, int]] = {}
        self.web_sessions: Dict[str, Dict[str, Optional[str]]] = {}
        self.next_message_id = 1
        self.load()

    def load(self) -> None:
        with self.lock:
            self.rooms = self._load_file(ROOMS_FILE, "rooms")
            self.users = self._load_file(USERS_FILE, "users")
            for room in self.rooms.values():
                room.setdefault("messages", [])
                room.setdefault("members", [])
            self._recompute_next_message_id()

    def _load_file(self, path: Path, key: str) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get(key, {})

    def _save_file(self, path: Path, key: str, value: Dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump({key: value}, handle, indent=2, sort_keys=True)

    def save_rooms(self) -> None:
        self._save_file(ROOMS_FILE, "rooms", self.rooms)

    def save_users(self) -> None:
        self._save_file(USERS_FILE, "users", self.users)

    def _recompute_next_message_id(self) -> None:
        max_id = 0
        for room in self.rooms.values():
            for message in room.get("messages", []):
                message_id = int(message.get("id", 0))
                if message_id > max_id:
                    max_id = message_id
        self.next_message_id = max_id + 1

    def set_user_active(self, username: str) -> None:
        self.active_user_counts[username] = self.active_user_counts.get(username, 0) + 1

    def set_user_inactive(self, username: str) -> None:
        if username not in self.active_user_counts:
            return
        remaining = self.active_user_counts[username] - 1
        if remaining <= 0:
            self.active_user_counts.pop(username, None)
        else:
            self.active_user_counts[username] = remaining

    def add_room_member(self, room_code: str, username: str) -> None:
        room_counts = self.room_user_counts.setdefault(room_code, {})
        room_counts[username] = room_counts.get(username, 0) + 1

    def remove_room_member(self, room_code: str, username: str) -> None:
        room_counts = self.room_user_counts.get(room_code)
        if not room_counts or username not in room_counts:
            return
        remaining = room_counts[username] - 1
        if remaining <= 0:
            room_counts.pop(username, None)
        else:
            room_counts[username] = remaining
        if not room_counts:
            self.room_user_counts.pop(room_code, None)

    def set_web_session(self, sid: str, username: str) -> None:
        existing = self.web_sessions.get(sid)
        if existing and existing.get("username") == username:
            return
        if existing:
            old_username = existing.get("username")
            old_room = existing.get("room_code")
            if old_username:
                self.set_user_inactive(old_username)
            if old_room and old_username:
                self.remove_room_member(old_room, old_username)
        self.web_sessions[sid] = {"username": username, "room_code": None}
        self.set_user_active(username)

    def set_web_session_room(self, sid: str, room_code: Optional[str]) -> None:
        session = self.web_sessions.get(sid)
        if not session:
            return
        username = session.get("username")
        old_room = session.get("room_code")
        if old_room and username and old_room != room_code:
            self.remove_room_member(old_room, username)
        if room_code and username:
            self.add_room_member(room_code, username)
        session["room_code"] = room_code

    def create_or_login_user(
        self, username: str, password: str, create: bool, ip: str
    ) -> Tuple[bool, str]:
        if not username or not password:
            return False, "Username and password are required."
        with self.lock:
            existing = self.users.get(username)
            if create:
                if existing:
                    return False, "Username already exists."
                self.users[username] = {
                    "password_hash": hash_secret(password),
                    "created_at": utc_now(),
                    "last_seen": utc_now(),
                    "last_ip": ip,
                }
                self.save_users()
                return True, "Profile created."
            if not existing:
                return False, "Profile not found."
            if not verify_secret(password, existing.get("password_hash", "")):
                return False, "Invalid password."
            existing["last_seen"] = utc_now()
            existing["last_ip"] = ip
            self.save_users()
            return True, "Profile loaded."

    def update_username(self, old: str, new: str, password: str) -> Tuple[bool, str]:
        if not new:
            return False, "New username is required."
        with self.lock:
            if new in self.users:
                return False, "Username already exists."
            user = self.users.get(old)
            if not user:
                return False, "Profile not found."
            if not verify_secret(password, user.get("password_hash", "")):
                return False, "Invalid password."
            self.users.pop(old)
            self.users[new] = user
            for room in self.rooms.values():
                for message in room.get("messages", []):
                    if message.get("sender") == old:
                        message["sender"] = new
                members = room.get("members", [])
                if old in members:
                    room["members"] = [new if member == old else member for member in members]
            if old in self.active_user_counts:
                self.active_user_counts[new] = self.active_user_counts.pop(old)
            for room_code, counts in self.room_user_counts.items():
                if old in counts:
                    counts[new] = counts.pop(old)
            for session in self.web_sessions.values():
                if session.get("username") == old:
                    session["username"] = new
            self.save_users()
            self.save_rooms()
            return True, "Username updated."

    def change_password(self, username: str, old: str, new: str) -> Tuple[bool, str]:
        if not new:
            return False, "New password is required."
        with self.lock:
            user = self.users.get(username)
            if not user:
                return False, "Profile not found."
            if not verify_secret(old, user.get("password_hash", "")):
                return False, "Invalid password."
            user["password_hash"] = hash_secret(new)
            user["last_seen"] = utc_now()
            self.save_users()
            return True, "Password updated."

    def create_room(self, name: str, password: str, owner: str) -> Tuple[bool, str, Optional[str]]:
        if not name:
            return False, "Room name is required.", None
        with self.lock:
            code = self._generate_room_code()
            self.rooms[code] = {
                "name": name,
                "password_hash": hash_secret(password) if password else None,
                "created_at": utc_now(),
                "owner": owner,
                "members": [owner],
                "messages": [],
            }
            self.save_rooms()
            return True, "Room created.", code

    def join_room(self, code: str, password: str, username: str) -> Tuple[bool, str]:
        with self.lock:
            room = self.rooms.get(code)
            if not room:
                return False, "Room not found."
            password_hash = room.get("password_hash")
            if password_hash and not verify_secret(password, password_hash):
                return False, "Invalid room password."
            members = room.setdefault("members", [])
            if username not in members:
                members.append(username)
            self.add_room_member(code, username)
            return True, "Joined room."

    def leave_room(self, code: str, username: str) -> None:
        with self.lock:
            self.remove_room_member(code, username)

    def add_message(
        self,
        room_code: str,
        username: str,
        text: str,
        ciphertext: Optional[str],
        iv: Optional[str],
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        if not text and not ciphertext:
            return False, "Message cannot be empty.", None
        if ciphertext and not iv:
            return False, "Missing encryption IV.", None
        with self.lock:
            room = self.rooms.get(room_code)
            if not room:
                return False, "Room not found.", None
            message = {
                "id": self.next_message_id,
                "ts": utc_now(),
                "sender": username,
            }
            if ciphertext:
                message["encrypted"] = True
                message["ciphertext"] = ciphertext
                message["iv"] = iv
            else:
                message["text"] = text
            self.next_message_id += 1
            room["messages"].append(message)
            if len(room["messages"]) > MAX_MESSAGES:
                room["messages"] = room["messages"][-MAX_MESSAGES:]
            self.save_rooms()
            return True, "Message sent.", message

    def get_messages(self, room_code: str, since_id: Optional[int]) -> Tuple[bool, str, List[Dict[str, Any]]]:
        with self.lock:
            room = self.rooms.get(room_code)
            if not room:
                return False, "Room not found.", []
            messages = room.get("messages", [])
            if since_id is None:
                return True, "Messages loaded.", messages
            filtered = [msg for msg in messages if int(msg.get("id", 0)) > since_id]
            return True, "Messages loaded.", filtered

    def list_rooms(self) -> List[Dict[str, Any]]:
        with self.lock:
            rooms = []
            for code, room in self.rooms.items():
                last_message = room.get("messages", [])[-1:] or []
                last_activity = last_message[0]["ts"] if last_message else room.get("created_at")
                active_count = sum(self.room_user_counts.get(code, {}).values())
                rooms.append(
                    {
                        "code": code,
                        "name": room.get("name"),
                        "requires_password": bool(room.get("password_hash")),
                        "last_activity": last_activity,
                        "active_count": active_count,
                    }
                )
            return rooms

    def list_active_users(self) -> List[str]:
        return sorted(self.active_user_counts.keys())

    def list_room_members(self, room_code: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
        with self.lock:
            room = self.rooms.get(room_code)
            if not room:
                return False, "Room not found.", []
            members = room.get("members", [])
            results = []
            for username in members:
                is_online = username in self.active_user_counts
                in_room = username in self.room_user_counts.get(room_code, {})
                user_data = self.users.get(username, {})
                results.append(
                    {
                        "username": username,
                        "online": is_online,
                        "in_room": in_room,
                        "last_seen": user_data.get("last_seen"),
                    }
                )
            return True, "Members loaded.", results

    def _generate_room_code(self) -> str:
        while True:
            code = secrets.token_hex(3).upper()
            if code not in self.rooms:
                return code


class ChatTCPHandler(socketserver.StreamRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.username: Optional[str] = None
        self.room_code: Optional[str] = None

    @property
    def state(self) -> ChatState:
        return self.server.state

    def handle(self) -> None:
        try:
            while True:
                line = self.rfile.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    self._send({"ok": False, "error": "Invalid JSON."})
                    continue
                response = self._handle_request(payload)
                self._send(response)
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self.room_code and self.username:
            self.state.leave_room(self.room_code, self.username)
        if self.username:
            self.state.set_user_inactive(self.username)

    def _send(self, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=True) + "\n"
        self.wfile.write(encoded.encode("utf-8"))

    def _require_username(self) -> Optional[Dict[str, Any]]:
        if not self.username:
            return {"ok": False, "error": "Not authenticated."}
        return None

    def _set_username(self, username: str) -> None:
        if self.username and self.username != username:
            self.state.set_user_inactive(self.username)
        if not self.username:
            self.state.set_user_active(username)
        self.username = username

    def _handle_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_type = payload.get("type")
        if request_type == "ping":
            return {"ok": True, "message": "pong"}
        if request_type == "profile_create":
            return self._handle_profile(create=True, payload=payload)
        if request_type == "profile_login":
            return self._handle_profile(create=False, payload=payload)
        if request_type == "profile_update_username":
            guard = self._require_username()
            if guard:
                return guard
            new_username = (payload.get("new_username") or "").strip()
            password = payload.get("password") or ""
            ok, message = self.state.update_username(self.username, new_username, password)
            if ok:
                self._set_username(new_username)
            return {"ok": ok, "message": message} if ok else {"ok": False, "error": message}
        if request_type == "profile_change_password":
            guard = self._require_username()
            if guard:
                return guard
            old_password = payload.get("old_password") or ""
            new_password = payload.get("new_password") or ""
            ok, message = self.state.change_password(self.username, old_password, new_password)
            return {"ok": ok, "message": message} if ok else {"ok": False, "error": message}
        if request_type == "rooms_list":
            return {"ok": True, "rooms": self.state.list_rooms()}
        if request_type == "room_members":
            guard = self._require_username()
            if guard:
                return guard
            code = (payload.get("code") or self.room_code or "").strip().upper()
            if not code:
                return {"ok": False, "error": "No room selected."}
            ok, message, members = self.state.list_room_members(code)
            if ok:
                return {"ok": True, "message": message, "members": members}
            return {"ok": False, "error": message}
        if request_type == "users_list":
            return {"ok": True, "users": self.state.list_active_users()}
        if request_type == "room_create":
            guard = self._require_username()
            if guard:
                return guard
            name = (payload.get("name") or "").strip()
            password = payload.get("password") or ""
            ok, message, code = self.state.create_room(name, password, self.username)
            if ok:
                return {"ok": True, "message": message, "code": code}
            return {"ok": False, "error": message}
        if request_type == "room_join":
            guard = self._require_username()
            if guard:
                return guard
            code = (payload.get("code") or "").strip().upper()
            password = payload.get("password") or ""
            ok, message = self.state.join_room(code, password, self.username)
            if ok:
                if self.room_code and self.room_code != code:
                    self.state.leave_room(self.room_code, self.username)
                self.room_code = code
                return {"ok": True, "message": message, "code": code}
            return {"ok": False, "error": message}
        if request_type == "room_leave":
            guard = self._require_username()
            if guard:
                return guard
            code = (payload.get("code") or self.room_code or "").strip().upper()
            if not code:
                return {"ok": False, "error": "No room to leave."}
            self.state.leave_room(code, self.username)
            if self.room_code == code:
                self.room_code = None
            return {"ok": True, "message": "Left room."}
        if request_type == "message_send":
            guard = self._require_username()
            if guard:
                return guard
            code = (payload.get("code") or self.room_code or "").strip().upper()
            if not code:
                return {"ok": False, "error": "No room selected."}
            text = (payload.get("text") or "").strip()
            ciphertext = payload.get("ciphertext")
            iv = payload.get("iv")
            ok, message, saved = self.state.add_message(code, self.username, text, ciphertext, iv)
            if ok:
                return {"ok": True, "message": message, "saved": saved}
            return {"ok": False, "error": message}
        if request_type == "messages_get":
            guard = self._require_username()
            if guard:
                return guard
            code = (payload.get("code") or self.room_code or "").strip().upper()
            if not code:
                return {"ok": False, "error": "No room selected."}
            since_id = payload.get("since_id")
            ok, message, messages = self.state.get_messages(code, since_id)
            if ok:
                return {"ok": True, "message": message, "messages": messages}
            return {"ok": False, "error": message}
        return {"ok": False, "error": "Unknown request."}

    def _handle_profile(self, create: bool, payload: Dict[str, Any]) -> Dict[str, Any]:
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        ok, message = self.state.create_or_login_user(
            username, password, create=create, ip=self.client_address[0]
        )
        if ok:
            self._set_username(username)
            return {"ok": True, "message": message}
        return {"ok": False, "error": message}


class ChatTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, server_address: Tuple[str, int], handler: Any, state: ChatState):
        super().__init__(server_address, handler)
        self.state = state


def create_app(state: ChatState):
    try:
        from flask import Flask, jsonify, render_template, request, session
    except ImportError as exc:
        raise SystemExit("Flask is required for the browser client. Install with: pip install flask") from exc

    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("VARTALAP_SECRET", secrets.token_hex(16))

    def get_sid() -> str:
        sid = session.get("sid")
        if not sid:
            sid = secrets.token_hex(8)
            session["sid"] = sid
        return sid

    def require_user() -> Optional[str]:
        return session.get("username")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/profile", methods=["POST"])
    def api_profile():
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        create = bool(data.get("create"))
        ok, message = state.create_or_login_user(username, password, create, request.remote_addr or "")
        if not ok:
            return jsonify({"ok": False, "error": message}), 400
        session["username"] = username
        sid = get_sid()
        state.set_web_session(sid, username)
        return jsonify({"ok": True, "message": message})

    @app.route("/api/profile/username", methods=["POST"])
    def api_profile_username():
        username = require_user()
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated."}), 401
        data = request.get_json(silent=True) or {}
        new_username = (data.get("new_username") or "").strip()
        password = data.get("password") or ""
        ok, message = state.update_username(username, new_username, password)
        if not ok:
            return jsonify({"ok": False, "error": message}), 400
        session["username"] = new_username
        sid = get_sid()
        state.set_web_session(sid, new_username)
        return jsonify({"ok": True, "message": message})

    @app.route("/api/profile/password", methods=["POST"])
    def api_profile_password():
        username = require_user()
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated."}), 401
        data = request.get_json(silent=True) or {}
        old_password = data.get("old_password") or ""
        new_password = data.get("new_password") or ""
        ok, message = state.change_password(username, old_password, new_password)
        if not ok:
            return jsonify({"ok": False, "error": message}), 400
        return jsonify({"ok": True, "message": message})

    @app.route("/api/rooms", methods=["GET"])
    def api_rooms_list():
        return jsonify({"ok": True, "rooms": state.list_rooms()})

    @app.route("/api/rooms", methods=["POST"])
    def api_rooms_create():
        username = require_user()
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated."}), 401
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        password = data.get("password") or ""
        ok, message, code = state.create_room(name, password, username)
        if not ok:
            return jsonify({"ok": False, "error": message}), 400
        return jsonify({"ok": True, "message": message, "code": code})

    @app.route("/api/rooms/join", methods=["POST"])
    def api_rooms_join():
        username = require_user()
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated."}), 401
        data = request.get_json(silent=True) or {}
        code = (data.get("code") or "").strip().upper()
        password = data.get("password") or ""
        ok, message = state.join_room(code, password, username)
        if not ok:
            return jsonify({"ok": False, "error": message}), 400
        session["room_code"] = code
        sid = get_sid()
        state.set_web_session_room(sid, code)
        return jsonify({"ok": True, "message": message, "code": code})

    @app.route("/api/rooms/leave", methods=["POST"])
    def api_rooms_leave():
        username = require_user()
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated."}), 401
        code = session.get("room_code")
        if not code:
            return jsonify({"ok": False, "error": "No active room."}), 400
        state.leave_room(code, username)
        sid = get_sid()
        state.set_web_session_room(sid, None)
        session.pop("room_code", None)
        return jsonify({"ok": True, "message": "Left room."})

    @app.route("/api/rooms/<code>/messages", methods=["GET"])
    def api_room_messages(code: str):
        code = code.strip().upper()
        since = request.args.get("since")
        since_id = int(since) if since and since.isdigit() else None
        ok, message, messages = state.get_messages(code, since_id)
        if not ok:
            return jsonify({"ok": False, "error": message}), 404
        return jsonify({"ok": True, "message": message, "messages": messages})

    @app.route("/api/rooms/<code>/members", methods=["GET"])
    def api_room_members(code: str):
        code = code.strip().upper()
        ok, message, members = state.list_room_members(code)
        if not ok:
            return jsonify({"ok": False, "error": message}), 404
        return jsonify({"ok": True, "message": message, "members": members})

    @app.route("/api/rooms/<code>/messages", methods=["POST"])
    def api_room_send_message(code: str):
        username = require_user()
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated."}), 401
        code = code.strip().upper()
        if session.get("room_code") != code:
            return jsonify({"ok": False, "error": "Join the room first."}), 400
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        ciphertext = data.get("ciphertext")
        iv = data.get("iv")
        ok, message, saved = state.add_message(code, username, text, ciphertext, iv)
        if not ok:
            return jsonify({"ok": False, "error": message}), 400
        return jsonify({"ok": True, "message": message, "saved": saved})

    @app.route("/api/users", methods=["GET"])
    def api_users():
        return jsonify({"ok": True, "users": state.list_active_users()})

    return app


def run_servers(
    tcp_host: str, tcp_port: int, http_host: str, http_port: int, no_web: bool
) -> None:
    state = ChatState()
    tcp_server = ChatTCPServer((tcp_host, tcp_port), ChatTCPHandler, state)
    tcp_thread = threading.Thread(target=tcp_server.serve_forever, daemon=True)
    tcp_thread.start()
    if no_web:
        tcp_thread.join()
        return
    app = create_app(state)
    app.run(host=http_host, port=http_port, threaded=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vartalap chat server")
    parser.add_argument("--host", default="0.0.0.0", help="Default host for TCP and HTTP")
    parser.add_argument("--tcp-host", help="TCP bind host (defaults to --host)")
    parser.add_argument("--http-host", help="HTTP bind host (defaults to --host)")
    parser.add_argument("--tcp-port", type=int, default=9009)
    parser.add_argument("--http-port", type=int, default=5000)
    parser.add_argument("--no-web", action="store_true", help="Run TCP server only")
    args = parser.parse_args()
    tcp_host = args.tcp_host or args.host
    http_host = args.http_host or args.host
    run_servers(tcp_host, args.tcp_port, http_host, args.http_port, args.no_web)


if __name__ == "__main__":
    main()
