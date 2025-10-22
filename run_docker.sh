#!/bin/bash
set -o pipefail

which uv
echo "[*] Starte dmScreen-Server ohne SSID"
/home/pi/.local/bin/uv run dmScreen-server --disable-networking
