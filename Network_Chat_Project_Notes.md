# Network Chat Application – Project Notes

## Overview

A simple network-based chat application.

### Architecture

```text
                Network
                   |
                Server
              (10.0.0.1)
              /       \
            PC1       PC2
             |         |
          Browser   Terminal
```

- **Server IP:** `10.0.0.1`
- **PC1:** Browser client
- **PC2:** Terminal client

---

# Application Flow

## Start

User chooses one of the following:

1. Create Room
2. Join Room
3. Existing Rooms
4. Profile
5. Exit

---

## Existing Rooms

Features:

- Show all available rooms
- Show room activity/status
- Join a room by selecting it
- Exit back to main menu

---

## Create Room

Inputs:

- Room Name
- Room Password

Notes:

- If the user has not configured a profile, display only the IP address.
- Otherwise display profile information.

Example:

```text
Enter Room Name:
Enter Room Password:
Room Created Successfully
```

---

## Join Room

Inputs:

- Room Code
- Password

Example:

```text
Enter Room Code:
Enter Password:
Connected Successfully
```

---

## Profile

Profile contains:

- Username
- Password

### Edit Username

```text
Current Username
↓
New Username
↓
Update
```

### Change Password

```text
Old Password
↓
New Password
↓
Update
```

---

# Terminal Interface Notes

## Startup

```text
Start
├── Browser Client
└── Terminal Client
```

### Browser Client

- Connects to chat server

### Terminal Client

Commands:

```text
chat
```

Features:

- Display all active users
- Display active chat rooms
- Find Person Message
- View Conversation
- View Messages

---

# Suggested Python Project Structure

```text
chat-app/
│
├── server.py
├── client_terminal.py
├── client_web.py
├── rooms.json
├── users.json
│
├── templates/
│   └── index.html
│
├── static/
│   ├── style.css
│   └── script.js
│
└── README.md
```

---

# Technologies

## Linux Terminal

- Python 3
- Socket Programming
- JSON Storage
- Threading
- Virtual Environment

## Browser Interface

- HTML
- CSS
- JavaScript
- Flask (optional)

---

# Future Features

- Private Messaging
- Room Password Protection
- User Profiles
- Room Activity Monitoring
- Message Search
- Conversation History
- Multiple Room Support
- Browser + Terminal Interoperability

---

# Basic Development Commands

## Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

## Install Flask

```bash
pip install flask
```

## Run Server

```bash
python server.py
```

## Run Terminal Client

```bash
python client_terminal.py
```

## Open Browser Client

```text
http://10.0.0.1:5000
```
