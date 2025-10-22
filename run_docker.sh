#!/bin/bash
set -o pipefail

which uv
echo "[*] Starte dmScreen-Server ohne SSID"
/usr/local/bin/uv run dmScreen-server --disable-networking
