#!/bin/bash
# start-ap.sh – startet AP auf wlan0 via nmcli (NetworkManager hotspot)
# Verwendung: sudo ./start-ap.sh

SSID="dmscreen"
PASS="dmscreen"
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

echo "[*] Starte AP \"$SSID\" über nmcli hotspot ..."

# Stoppe eventuell existierenden Hotspot
nmcli connection delete Hotspot >/dev/null 2>&1 || true

# Starte Hotspot auf wlan0
# nmcli device wifi hotspot ifname <interface> ssid <ssid> password <password>
if nmcli device wifi hotspot ifname "$IFACE" ssid "$SSID" password "$PASS"; then
    echo "[+] AP erfolgreich gestartet."
    echo "    SSID: \"$SSID\""
    echo "    Passwort: \"$PASS\""
    
    # Warte kurz auf IP-Zuweisung
    sleep 2
    
    # Zeige IP-Adresse an
    WLAN_IP=$(nmcli -t -f IP4.ADDRESS dev show "$IFACE" 2>/dev/null | grep 'IP4.ADDRESS' | cut -d: -f2 | cut -d/ -f1 | head -n1)
    if [ -n "$WLAN_IP" ]; then
        echo "    AP-IP (wlan0): $WLAN_IP"
    else
        echo "    AP-IP (wlan0): 10.42.0.1 (Standard)"
    fi
    
    exit 0
else
    echo "[!] Fehler beim Starten des AP. Prüfe:"
    echo "    - Ist NetworkManager aktiv? (systemctl status NetworkManager)"
    echo "    - Ist wlan0 verfügbar? (nmcli device status)"
    echo "    - Logs: journalctl -u NetworkManager -b"
    exit 1
fi
