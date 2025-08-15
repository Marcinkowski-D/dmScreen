#!/bin/bash
# forget-wifi.sh – trennt aktuelles WLAN und entfernt dessen Block aus wpa_supplicant-wlan0.conf

IFACE="wlan0"
WPA_IF_FILE="/etc/wpa_supplicant/wpa_supplicant-${IFACE}.conf"

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

rfkill unblock wifi 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true

# SSID ermitteln
SSID="$(wpa_cli -i "$IFACE" status 2>/dev/null | awk -F= '/^ssid=/{print $2}')"
[ -z "$SSID" ] && SSID="$(iwgetid -r 2>/dev/null)"
[ -z "$SSID" ] && { echo "[!] Nicht mit einem WLAN verbunden."; exit 1; }

echo "[*] Trenne WLAN \"$SSID\" und entferne Zugangsdaten..."

# Disconnect + DHCP-Lease freigeben (nur wlan0)
wpa_cli -i "$IFACE" disconnect >/dev/null 2>&1 || true
dhclient -r "$IFACE" >/dev/null 2>&1 || true
pkill -f "dhclient.*$IFACE" >/dev/null 2>&1 || true
ip addr flush dev "$IFACE" 2>/dev/null || true

# Konfig anpassen
[ -f "$WPA_IF_FILE" ] || { echo "[!] $WPA_IF_FILE nicht gefunden."; exit 1; }
cp "$WPA_IF_FILE" "${WPA_IF_FILE}.bak.$(date +%s)"

awk -v ssid="$SSID" '
BEGIN{inblk=0}
{
  if($0 ~ /^network=\{/){inblk=1; buf=$0 ORS; next}
  if(inblk){
    buf=buf $0 ORS
    if($0 ~ /^\}/){
      if(buf ~ "ssid=\""ssid"\""){next} else {printf "%s", buf}
      inblk=0; buf=""
    }
    next
  }
  print
}' "$WPA_IF_FILE" > "${WPA_IF_FILE}.tmp" && mv "${WPA_IF_FILE}.tmp" "$WPA_IF_FILE"

wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true

WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] WLAN \"$SSID\" getrennt und vergessen."
echo "    WLAN-IP: ${WLAN_IP:- -}"
