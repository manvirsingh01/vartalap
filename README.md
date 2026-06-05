# Vartalap

Network chat app with a TCP terminal client and a Flask browser UI.

## Quick start

```bash
python3 -m venv .venv
./.venv/bin/pip install flask cryptography
./.venv/bin/python server.py --tcp-host 0.0.0.0 --http-host 127.0.0.1
```

Browser UI (via Flask):
`http://127.0.0.1:5000`

Terminal client:
```bash
python3 client_terminal.py --host 127.0.0.1 --port 9009
```

## install.sh (Linux)

```bash
./install.sh --with-systemd --with-apache example.com
```

What it does:
- Creates `.venv` and installs Flask + cryptography
- (Optional) Sets up a systemd service
- (Optional) Creates an Apache reverse proxy config

## Apache reverse proxy

The installer writes `/etc/apache2/sites-available/vartalap.conf` from `apache-vartalap.conf`.
If you want to do it manually:

```bash
sudo a2enmod proxy proxy_http headers
sudo a2ensite vartalap.conf
sudo systemctl reload apache2
```

Make sure the Flask server is running on `127.0.0.1:5000` and the TCP port `9009`
is open for terminal clients.

## Message encryption

Messages are AES-GCM encrypted on the clients. The key is derived from the room
password, or from the room code if no password is set. The browser UI requires
HTTPS (or localhost) so the Web Crypto API is available.
