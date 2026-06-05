#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
TCP_PORT=9009
HTTP_PORT=5000
TCP_HOST="0.0.0.0"
HTTP_HOST="127.0.0.1"
WITH_SYSTEMD=0
WITH_APACHE=0
DOMAIN=""
SERVICE_USER=""

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --with-systemd            Install a systemd service (requires root)
  --with-apache DOMAIN      Install Apache reverse proxy config (requires root)
  --domain DOMAIN           Domain name for Apache config
  --tcp-host HOST           TCP bind host (default: 0.0.0.0)
  --tcp-port PORT           TCP port (default: 9009)
  --http-host HOST          HTTP bind host (default: 127.0.0.1)
  --http-port PORT          HTTP port (default: 5000)
  --service-user USER       systemd User= value (default: sudo user)
  -h, --help                Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-systemd)
      WITH_SYSTEMD=1
      ;;
    --with-apache)
      WITH_APACHE=1
      if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
        DOMAIN="${2}"
        shift
      fi
      ;;
    --domain)
      DOMAIN="${2:-}"
      shift
      ;;
    --tcp-host)
      TCP_HOST="${2:-}"
      shift
      ;;
    --tcp-port)
      TCP_PORT="${2:-}"
      shift
      ;;
    --http-host)
      HTTP_HOST="${2:-}"
      shift
      ;;
    --http-port)
      HTTP_PORT="${2:-}"
      shift
      ;;
    --service-user)
      SERVICE_USER="${2:-}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required."
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
"$VENV_DIR/bin/pip" install flask >/dev/null

if [[ "$WITH_SYSTEMD" -eq 1 || "$WITH_APACHE" -eq 1 ]]; then
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Re-run with sudo to install systemd/Apache configuration."
    exit 1
  fi
fi

if [[ "$WITH_SYSTEMD" -eq 1 ]]; then
  if [[ -z "$SERVICE_USER" ]]; then
    SERVICE_USER="${SUDO_USER:-$USER}"
  fi
  cat > /etc/systemd/system/vartalap.service <<EOF
[Unit]
Description=Vartalap Chat Server
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${ROOT_DIR}
ExecStart=${VENV_DIR}/bin/python ${ROOT_DIR}/server.py --tcp-host ${TCP_HOST} --http-host ${HTTP_HOST} --tcp-port ${TCP_PORT} --http-port ${HTTP_PORT}
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl enable --now vartalap
  else
    echo "systemctl not found. Create a service manually or run server.py directly."
  fi
fi

if [[ "$WITH_APACHE" -eq 1 ]]; then
  if [[ -z "$DOMAIN" ]]; then
    echo "Domain is required for Apache config. Use --with-apache DOMAIN or --domain DOMAIN."
    exit 1
  fi
  if [[ ! -f "${ROOT_DIR}/apache-vartalap.conf" ]]; then
    echo "apache-vartalap.conf not found in project root."
    exit 1
  fi
  sed "s/YOUR_DOMAIN/${DOMAIN}/g" "${ROOT_DIR}/apache-vartalap.conf" \
    > /etc/apache2/sites-available/vartalap.conf
  if command -v a2enmod >/dev/null 2>&1; then
    a2enmod proxy proxy_http headers >/dev/null
  fi
  if command -v a2ensite >/dev/null 2>&1; then
    a2ensite vartalap.conf >/dev/null
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files | grep -q '^apache2\.service'; then
      systemctl reload apache2
    elif systemctl list-unit-files | grep -q '^httpd\.service'; then
      systemctl reload httpd
    fi
  fi
fi

cat <<EOF
Install complete.

Run manually:
  ${VENV_DIR}/bin/python ${ROOT_DIR}/server.py --tcp-host ${TCP_HOST} --http-host ${HTTP_HOST} --tcp-port ${TCP_PORT} --http-port ${HTTP_PORT}

Terminal client:
  python3 ${ROOT_DIR}/client_terminal.py --host <server-ip> --port ${TCP_PORT}
EOF
