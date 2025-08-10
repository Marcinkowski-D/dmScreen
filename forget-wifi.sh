#!/bin/bash
# forget-wifi.sh
# Trennt das aktuelle WLAN und löscht die Zugangsdaten

# --- Root prüfen ---
if [ "$EUID" -ne 0 ]; then
    echo "Bitte mit sudo ausführen."
    exit 1
fi

WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"

# --- Aktuelle SSID ermitteln ---
SSID=$(iwgetid -r)

if [ -z "$SSID" ]; then
    echo "[!] Nicht mit einem WLAN verbunden."
    exit 1
fi

echo "[*] Trenne von WLAN: $SSID"

# --- WLAN trennen ---
wpa_cli -i wlan0 disconnect >/dev/null 2>&1

# --- Zugangsdaten entfernen ---
if grep -q "ssid=\"$SSID\"" "$WPA_FILE"; then
    echo "[*] Entferne $SSID aus $WPA_FILE..."
    # Backup erstellen
    cp "$WPA_FILE" "${WPA_FILE}.bak.$(date +%s)"
    # Mit awk den entsprechenden network-Block löschen
    awk -v ssid="$SSID" '
    BEGIN {in_block=0}
    {
        if ($0 ~ "network=") {
            in_block=0
        }
    }
    {
        if ($0 ~ "ssid=\""ssid"\"") {
            in_block=1
        }
        if (!in_block) {
            print $0
        }
    }' "$WPA_FILE" > "${WPA_FILE}.tmp" && mv "${WPA_FILE}.tmp" "$WPA_FILE"
else
    echo "[!] SSID $SSID nicht in $WPA_FILE gefunden."
fi

# --- WLAN-Dienst neu starten ---
systemctl restart dhcpcd

echo "[+] WLAN $SSID wurde getrennt und entfernt."
