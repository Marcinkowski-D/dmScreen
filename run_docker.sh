#!/bin/bash
set -o pipefail

echo "[*] Starte dmScreen-Server ohne SSID"
/home/pi/.local/bin/uv run dmScreen-server --disable-networking
