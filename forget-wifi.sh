#!/bin/bash
# forget-wifi.sh – trennt aktuelles WLAN und entfernt dessen Verbindung via nmcli (NetworkManager)
# Verwendung: sudo ./forget-wifi.sh [SSID]
# Ohne SSID-Parameter wird das aktuell verbundene WLAN vergessen

IFACE="wlan0"
SSID="$1"

set -o pipefail

# Root-Check
[ "$EUID" -eq 0 ] || { echo "[!] Bitte mit sudo ausführen."; exit 1; }

# nmcli verfügbar?
if ! command -v nmcli >/dev/null 2>&1; then
    echo "[!] nmcli nicht gefunden. Bitte NetworkManager installieren:"
    echo "    sudo apt-get install -y network-manager"
    exit 1
fi

# Wenn keine SSID angegeben, ermittle aktuelle Verbindung
if [ -z "$SSID" ]; then
    # Hole aktive WiFi-Verbindung
    SSID=$(nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes:' | cut -d: -f2)
    
    if [ -z "$SSID" ]; then
        echo "[!] Nicht mit einem WLAN verbunden und keine SSID angegeben."
        echo "    Nutzung: sudo $0 [SSID]"
        exit 1
    fi
    
    echo "[*] Erkannte aktuelle Verbindung: \"$SSID\""
fi

echo "[*] Trenne und vergesse WLAN \"$SSID\"..."

# Verbindung löschen (disconnectet automatisch wenn aktiv)
if nmcli connection delete "$SSID" 2>/dev/null; then
    echo "[+] WLAN \"$SSID\" erfolgreich getrennt und vergessen."
else
    echo "[*] Verbindung \"$SSID\" nicht gefunden oder bereits gelöscht."
    
    # Versuche auch system-connections direkt zu löschen (falls vorhanden)
    if [ -f "/etc/NetworkManager/system-connections/$SSID" ]; then
        rm -f "/etc/NetworkManager/system-connections/$SSID"
        echo "[*] Verbindungsdatei manuell entfernt."
    elif [ -f "/etc/NetworkManager/system-connections/$SSID.nmconnection" ]; then
        rm -f "/etc/NetworkManager/system-connections/$SSID.nmconnection"
        echo "[*] Verbindungsdatei manuell entfernt."
    fi
    
    # NetworkManager neu laden
    nmcli connection reload 2>/dev/null || true
fi

# Entferne auch preconfigured.nmconnection falls vorhanden
if [ -f "/etc/NetworkManager/system-connections/preconfigured.nmconnection" ]; then
    rm -f "/etc/NetworkManager/system-connections/preconfigured.nmconnection"
    nmcli connection reload 2>/dev/null || true
    echo "[*] Vorkonfigurierte Verbindung entfernt."
fi

# Interface-Status anzeigen
WLAN_STATUS=$(nmcli -t -f DEVICE,STATE dev status | grep "^$IFACE:" | cut -d: -f2)
echo "    wlan0 Status: ${WLAN_STATUS:-unbekannt}"

# IP-Adresse anzeigen (falls noch vorhanden)
WLAN_IP=$(nmcli -t -f IP4.ADDRESS dev show "$IFACE" 2>/dev/null | grep 'IP4.ADDRESS' | cut -d: -f2 | cut -d/ -f1 | head -n1)
echo "    WLAN-IP (wlan0): ${WLAN_IP:--}"

exit 0
