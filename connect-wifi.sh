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
IP=$(hostname -I | awk '{print $1}')
if [ -n "$IP" ]; then
    echo "[+] Erfolgreich verbunden. IP-Adresse: $IP"
else
    echo "[!] Keine IP erhalten. Bitte WLAN-Daten prüfen."
fi
