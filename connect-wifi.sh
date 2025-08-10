#!/bin/bash
# connect-wifi.sh
# Nutzung: sudo ./connect-wifi.sh "SSID" "PASSWORT"

SSID="$1"
PASS="$2"

# --- Parameter prüfen ---
if [ -z "$SSID" ] || [ -z "$PASS" ]; then
    echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""
    exit 1
fi

# --- Root prüfen ---
if [ "$EUID" -ne 0 ]; then
    echo "Bitte mit sudo ausführen."
    exit 1
fi

echo "[*] Verbinde mit SSID: $SSID"

# --- Backup bestehender Konfiguration ---
WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"
if [ -f "$WPA_FILE" ]; then
    cp "$WPA_FILE" "${WPA_FILE}.bak.$(date +%s)"
fi

# --- Netzwerkblock erstellen ---
cat <<EOF > "$WPA_FILE"
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE

network={
    ssid="$SSID"
    psk="$PASS"
}
EOF

# --- Dienst neu starten ---
echo "[*] WLAN-Dienst wird neu gestartet..."
wpa_cli -i wlan0 reconfigure 2>/dev/null || systemctl restart dhcpcd

# --- Verbindung prüfen ---
sleep 5
WLAN_IP=$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
ETH_IP=$(ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}')

if [ -n "$WLAN_IP" ]; then
    echo "[+] Erfolgreich mit $SSID verbunden."
    echo "    WLAN-IP: $WLAN_IP"
    if [ -n "$ETH_IP" ]; then
        echo "    LAN-IP:  $ETH_IP"
    fi
else
    echo "[!] Keine WLAN-IP erhalten. Bitte WLAN-Daten prüfen."
    if [ -n "$ETH_IP" ]; then
        echo "    LAN-IP:  $ETH_IP (über Kabel verbunden)"
    fi
fi
