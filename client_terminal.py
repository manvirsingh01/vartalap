#!/usr/bin/env python3
import argparse
import base64
import json
import os
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class TerminalClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port))
        self.reader = self.sock.makefile("r")
        self.writer = self.sock.makefile("w")
        self.username: Optional[str] = None
        self.room_code: Optional[str] = None
        self.room_password: Optional[str] = None
        self.last_message_id = 0
        self.request_lock = threading.Lock()
        self.print_lock = threading.Lock()
        self.stop_poll = threading.Event()
        self.poll_thread: Optional[threading.Thread] = None

    def close(self) -> None:
        self.stop_polling()
        try:
            self.reader.close()
            self.writer.close()
            self.sock.close()
        except OSError:
            pass

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.request_lock:
            self.writer.write(json.dumps(payload) + "\n")
            self.writer.flush()
            line = self.reader.readline()
            if not line:
                raise ConnectionError("Server disconnected.")
            return json.loads(line)

    def print_safe(self, message: str) -> None:
        with self.print_lock:
            print(message)

    def _derive_key(self) -> bytes:
        if not self.room_code:
            raise ValueError("No room selected.")
        password = self.room_password or self.room_code
        salt = f"vartalap:{self.room_code}".encode("utf-8")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000
        )
        return kdf.derive(password.encode("utf-8"))

    def _encrypt_message(self, text: str) -> Tuple[str, str]:
        key = self._derive_key()
        iv = os.urandom(12)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, text.encode("utf-8"), None)
        return (
            base64.b64encode(ciphertext).decode("utf-8"),
            base64.b64encode(iv).decode("utf-8"),
        )

    def _decrypt_message(self, ciphertext_b64: str, iv_b64: str) -> Optional[str]:
        key = self._derive_key()
        aesgcm = AESGCM(key)
        ciphertext = base64.b64decode(ciphertext_b64)
        iv = base64.b64decode(iv_b64)
        try:
            plaintext = aesgcm.decrypt(iv, ciphertext, None)
        except InvalidTag:
            return None
        return plaintext.decode("utf-8")

    def profile_menu(self) -> None:
        while True:
            print("\nProfile")
            print("1. Create Profile")
            print("2. Login")
            print("3. Exit")
            choice = input("Select: ").strip()
            if choice == "1":
                if self._create_profile():
                    return
            elif choice == "2":
                if self._login():
                    return
            elif choice == "3":
                raise SystemExit(0)
            else:
                print("Invalid choice.")

    def _create_profile(self) -> bool:
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        response = self.request(
            {"type": "profile_create", "username": username, "password": password}
        )
        if response.get("ok"):
            self.username = username
            self.print_safe(response.get("message"))
            return True
        self.print_safe(response.get("error"))
        return False

    def _login(self) -> bool:
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        response = self.request({"type": "profile_login", "username": username, "password": password})
        if response.get("ok"):
            self.username = username
            self.print_safe(response.get("message"))
            return True
        self.print_safe(response.get("error"))
        return False

    def main_menu(self) -> None:
        while True:
            print("\nMain Menu")
            print("1. Create Room")
            print("2. Join Room")
            print("3. Existing Rooms")
            print("4. Profile")
            print("5. Exit")
            choice = input("Select: ").strip()
            if choice == "1":
                self.create_room()
            elif choice == "2":
                self.join_room()
            elif choice == "3":
                self.show_rooms()
            elif choice == "4":
                self.profile_settings()
            elif choice == "5":
                break
            else:
                self.print_safe("Invalid choice.")

    def create_room(self) -> None:
        name = input("Room Name: ").strip()
        password = input("Room Password (optional): ").strip()
        response = self.request({"type": "room_create", "name": name, "password": password})
        if response.get("ok"):
            self.print_safe(f"Room created. Code: {response.get('code')}")
        else:
            self.print_safe(response.get("error"))

    def join_room(self) -> None:
        code = input("Room Code: ").strip().upper()
        password = input("Room Password: ").strip()
        response = self.request({"type": "room_join", "code": code, "password": password})
        if response.get("ok"):
            self.room_code = code
            self.room_password = password
            self.last_message_id = 0
            self.print_safe("Connected successfully.")
            self.chat_loop()
        else:
            self.print_safe(response.get("error"))

    def show_rooms(self) -> None:
        response = self.request({"type": "rooms_list"})
        if not response.get("ok"):
            self.print_safe(response.get("error"))
            return
        rooms = response.get("rooms", [])
        if not rooms:
            self.print_safe("No rooms available.")
            return
        self.print_safe("\nRooms")
        for room in rooms:
            lock = "Yes" if room.get("requires_password") else "No"
            self.print_safe(
                f"{room.get('code')} | {room.get('name')} | Active: {room.get('active_count')} | Password: {lock}"
            )

    def profile_settings(self) -> None:
        while True:
            print("\nProfile Settings")
            print("1. Edit Username")
            print("2. Change Password")
            print("3. Back")
            choice = input("Select: ").strip()
            if choice == "1":
                self.update_username()
            elif choice == "2":
                self.change_password()
            elif choice == "3":
                return
            else:
                self.print_safe("Invalid choice.")

    def update_username(self) -> None:
        new_username = input("New Username: ").strip()
        password = input("Current Password: ").strip()
        response = self.request(
            {
                "type": "profile_update_username",
                "new_username": new_username,
                "password": password,
            }
        )
        if response.get("ok"):
            self.username = new_username
            self.print_safe(response.get("message"))
        else:
            self.print_safe(response.get("error"))

    def change_password(self) -> None:
        old_password = input("Old Password: ").strip()
        new_password = input("New Password: ").strip()
        response = self.request(
            {
                "type": "profile_change_password",
                "old_password": old_password,
                "new_password": new_password,
            }
        )
        if response.get("ok"):
            self.print_safe(response.get("message"))
        else:
            self.print_safe(response.get("error"))

    def chat_loop(self) -> None:
        self.print_safe(
            "\nChat Commands: /leave, /refresh, /history, /find <username>, /users, /members"
        )
        self.refresh_messages(show_all=True, silent=False)
        self.start_polling()
        while True:
            message = input("> ").strip()
            if not message:
                continue
            if message.startswith("/"):
                if message == "/leave":
                    self.leave_room()
                    return
                if message == "/refresh":
                    self.refresh_messages(show_all=False, silent=False)
                    continue
                if message == "/history":
                    self.refresh_messages(show_all=True, silent=False)
                    continue
                if message.startswith("/find "):
                    target = message.split(" ", 1)[1].strip()
                    self.find_user_messages(target)
                    continue
                if message == "/users":
                    self.show_users()
                    continue
                if message == "/members":
                    self.show_room_members()
                    continue
                self.print_safe("Unknown command.")
                continue
            try:
                ciphertext, iv = self._encrypt_message(message)
            except ValueError as exc:
                self.print_safe(str(exc))
                continue
            response = self.request(
                {"type": "message_send", "ciphertext": ciphertext, "iv": iv}
            )
            if not response.get("ok"):
                self.print_safe(response.get("error"))
                continue
            self.refresh_messages(show_all=False, silent=True)

    def leave_room(self) -> None:
        self.stop_polling()
        response = self.request({"type": "room_leave", "code": self.room_code})
        if response.get("ok"):
            self.print_safe(response.get("message"))
        else:
            self.print_safe(response.get("error"))
        self.room_code = None
        self.room_password = None

    def refresh_messages(self, show_all: bool, silent: bool) -> None:
        since_id = None if show_all else self.last_message_id
        response = self.request({"type": "messages_get", "since_id": since_id})
        if not response.get("ok"):
            if not silent:
                self.print_safe(response.get("error"))
            return
        messages = response.get("messages", [])
        if not messages:
            if show_all and not silent:
                self.print_safe("No messages yet.")
            return
        self._print_messages(messages)

    def _print_messages(self, messages: List[Dict[str, Any]]) -> None:
        for message in messages:
            self.last_message_id = max(self.last_message_id, int(message.get("id", 0)))
            text = message.get("text")
            if not text and message.get("ciphertext") and message.get("iv"):
                text = self._decrypt_message(message.get("ciphertext"), message.get("iv"))
                if text is None:
                    text = "[Encrypted message - unable to decrypt]"
            self.print_safe(f"[{message.get('ts')}] {message.get('sender')}: {text}")

    def find_user_messages(self, username: str) -> None:
        response = self.request({"type": "messages_get"})
        if not response.get("ok"):
            self.print_safe(response.get("error"))
            return
        messages = [
            msg for msg in response.get("messages", []) if msg.get("sender") == username
        ]
        if not messages:
            self.print_safe("No messages found.")
            return
        self._print_messages(messages)

    def show_users(self) -> None:
        response = self.request({"type": "users_list"})
        if not response.get("ok"):
            self.print_safe(response.get("error"))
            return
        users = response.get("users", [])
        if not users:
            self.print_safe("No active users.")
            return
        self.print_safe("Active users: " + ", ".join(users))

    def show_room_members(self) -> None:
        response = self.request({"type": "room_members", "code": self.room_code})
        if not response.get("ok"):
            self.print_safe(response.get("error"))
            return
        members = response.get("members", [])
        if not members:
            self.print_safe("No members found.")
            return
        self.print_safe("\nRoom Members")
        for member in members:
            status = "Online" if member.get("online") else "Offline"
            in_room = "In room" if member.get("in_room") else "Away"
            self.print_safe(f"{member.get('username')} | {status} | {in_room}")

    def start_polling(self) -> None:
        if self.poll_thread and self.poll_thread.is_alive():
            return
        self.stop_poll.clear()
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def stop_polling(self) -> None:
        self.stop_poll.set()
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_thread.join(timeout=1)
        self.poll_thread = None

    def _poll_loop(self) -> None:
        while not self.stop_poll.is_set():
            if self.room_code:
                try:
                    self.refresh_messages(show_all=False, silent=True)
                except ConnectionError:
                    self.stop_poll.set()
                    return
            self.stop_poll.wait(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vartalap terminal client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9009)
    args = parser.parse_args()
    client = TerminalClient(args.host, args.port)
    try:
        client.profile_menu()
        client.main_menu()
    except (ConnectionError, KeyboardInterrupt) as exc:
        print(f"Disconnected: {exc}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
