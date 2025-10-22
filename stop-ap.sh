#!/bin/bash
# stop-ap.sh – beendet den AP auf wlan0 via nmcli (NetworkManager)
# Verwendung: sudo ./stop-ap.sh

IFACE="wlan0"

set -o pipefail

# Root-Check
[ "$EUID" -eq 0 ] || { echo "[!] Bitte mit sudo ausführen."; exit 1; }

# nmcli verfügbar?
if ! command -v nmcli >/dev/null 2>&1; then
    echo "[!] nmcli nicht gefunden. Bitte NetworkManager installieren:"
    echo "    sudo apt-get install -y network-manager"
    exit 1
fi

echo "[*] Stoppe AP-Modus (ohne Auto-Connect)..."

# Hotspot-Verbindung löschen
if nmcli connection delete Hotspot 2>/dev/null; then
    echo "[+] Hotspot erfolgreich gestoppt."
else
    echo "[*] Kein aktiver Hotspot gefunden (oder bereits gestoppt)."
fi

# Interface-Status anzeigen
WLAN_STATUS=$(nmcli -t -f DEVICE,STATE dev status | grep "^$IFACE:" | cut -d: -f2)
echo "    wlan0 Status: ${WLAN_STATUS:-unbekannt}"

# IP-Adresse anzeigen (falls vorhanden)
WLAN_IP=$(nmcli -t -f IP4.ADDRESS dev show "$IFACE" 2>/dev/null | grep 'IP4.ADDRESS' | cut -d: -f2 | cut -d/ -f1 | head -n1)
echo "    WLAN-IP (wlan0): ${WLAN_IP:--}"

exit 0
