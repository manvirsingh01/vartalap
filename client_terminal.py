#!/usr/bin/env python3
import argparse
import json
import socket
from typing import Any, Dict, List, Optional


class TerminalClient:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port))
        self.reader = self.sock.makefile("r")
        self.writer = self.sock.makefile("w")
        self.username: Optional[str] = None
        self.room_code: Optional[str] = None
        self.last_message_id = 0

    def close(self) -> None:
        try:
            self.reader.close()
            self.writer.close()
            self.sock.close()
        except OSError:
            pass

    def request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.writer.write(json.dumps(payload) + "\n")
        self.writer.flush()
        line = self.reader.readline()
        if not line:
            raise ConnectionError("Server disconnected.")
        return json.loads(line)

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
            print(response.get("message"))
            return True
        print(response.get("error"))
        return False

    def _login(self) -> bool:
        username = input("Username: ").strip()
        password = input("Password: ").strip()
        response = self.request({"type": "profile_login", "username": username, "password": password})
        if response.get("ok"):
            self.username = username
            print(response.get("message"))
            return True
        print(response.get("error"))
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
                print("Invalid choice.")

    def create_room(self) -> None:
        name = input("Room Name: ").strip()
        password = input("Room Password (optional): ").strip()
        response = self.request({"type": "room_create", "name": name, "password": password})
        if response.get("ok"):
            print(f"Room created. Code: {response.get('code')}")
        else:
            print(response.get("error"))

    def join_room(self) -> None:
        code = input("Room Code: ").strip().upper()
        password = input("Room Password: ").strip()
        response = self.request({"type": "room_join", "code": code, "password": password})
        if response.get("ok"):
            self.room_code = code
            self.last_message_id = 0
            print("Connected successfully.")
            self.chat_loop()
        else:
            print(response.get("error"))

    def show_rooms(self) -> None:
        response = self.request({"type": "rooms_list"})
        if not response.get("ok"):
            print(response.get("error"))
            return
        rooms = response.get("rooms", [])
        if not rooms:
            print("No rooms available.")
            return
        print("\nRooms")
        for room in rooms:
            lock = "Yes" if room.get("requires_password") else "No"
            print(
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
                print("Invalid choice.")

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
            print(response.get("message"))
        else:
            print(response.get("error"))

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
            print(response.get("message"))
        else:
            print(response.get("error"))

    def chat_loop(self) -> None:
        print("\nChat Commands: /leave, /refresh, /history, /find <username>, /users")
        self.refresh_messages(show_all=True)
        while True:
            message = input("> ").strip()
            if not message:
                continue
            if message.startswith("/"):
                if message == "/leave":
                    self.leave_room()
                    return
                if message == "/refresh":
                    self.refresh_messages(show_all=False)
                    continue
                if message == "/history":
                    self.refresh_messages(show_all=True)
                    continue
                if message.startswith("/find "):
                    target = message.split(" ", 1)[1].strip()
                    self.find_user_messages(target)
                    continue
                if message == "/users":
                    self.show_users()
                    continue
                print("Unknown command.")
                continue
            response = self.request({"type": "message_send", "text": message})
            if not response.get("ok"):
                print(response.get("error"))
                continue
            self.refresh_messages(show_all=False)

    def leave_room(self) -> None:
        response = self.request({"type": "room_leave", "code": self.room_code})
        if response.get("ok"):
            print(response.get("message"))
        else:
            print(response.get("error"))
        self.room_code = None

    def refresh_messages(self, show_all: bool) -> None:
        since_id = None if show_all else self.last_message_id
        response = self.request({"type": "messages_get", "since_id": since_id})
        if not response.get("ok"):
            print(response.get("error"))
            return
        messages = response.get("messages", [])
        if not messages:
            if show_all:
                print("No messages yet.")
            return
        self._print_messages(messages)

    def _print_messages(self, messages: List[Dict[str, Any]]) -> None:
        for message in messages:
            self.last_message_id = max(self.last_message_id, int(message.get("id", 0)))
            print(f"[{message.get('ts')}] {message.get('sender')}: {message.get('text')}")

    def find_user_messages(self, username: str) -> None:
        response = self.request({"type": "messages_get"})
        if not response.get("ok"):
            print(response.get("error"))
            return
        messages = [
            msg for msg in response.get("messages", []) if msg.get("sender") == username
        ]
        if not messages:
            print("No messages found.")
            return
        self._print_messages(messages)

    def show_users(self) -> None:
        response = self.request({"type": "users_list"})
        if not response.get("ok"):
            print(response.get("error"))
            return
        users = response.get("users", [])
        if not users:
            print("No active users.")
            return
        print("Active users: " + ", ".join(users))


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
