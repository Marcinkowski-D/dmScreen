#!/bin/bash
# stop-ap.sh
# Beendet den Access Point und stellt den ursprünglichen Netzwerkmodus wieder her

IFACE="wlan0"
WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"
DNSMASQ_CONF="/etc/dnsmasq.conf"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
INTERFACES_FILE="/etc/network/interfaces.d/$IFACE"

# --- Root prüfen ---
if [ "$EUID" -ne 0 ]; then
    echo "Bitte mit sudo ausführen."
    exit 1
fi

echo "[*] Stoppe Access Point..."

# --- Dienste stoppen ---
systemctl stop hostapd
systemctl stop dnsmasq
systemctl disable hostapd
systemctl disable dnsmasq

# --- Hostapd-Config leeren ---
if [ -f "$HOSTAPD_CONF" ]; then
    rm -f "$HOSTAPD_CONF"
fi

# --- dnsmasq-Config zurücksetzen ---
if [ -f "${DNSMASQ_CONF}.bak" ]; then
    mv "${DNSMASQ_CONF}.bak" "$DNSMASQ_CONF"
else
    # Falls kein Backup existiert, Datei leeren
    echo "" > "$DNSMASQ_CONF"
fi

# --- Statische IP entfernen ---
if [ -f "$INTERFACES_FILE" ]; then
    rm -f "$INTERFACES_FILE"
fi

# --- wlan0 auf DHCP zurücksetzen ---
dhclient -r $IFACE 2>/dev/null
dhclient $IFACE

# --- Netzwerkdienst neustarten ---
systemctl restart dhcpcd

# --- Verbindung prüfen ---
sleep 2
IP=$(hostname -I | awk '{print $1}')
if [ -n "$IP" ]; then
    echo "[+] Netzwerk zurückgesetzt. Aktuelle IP: $IP"
else
    echo "[!] Kein Netzwerk verbunden. Jetzt kannst du wieder ein WLAN verbinden oder einen AP starten."
fi
