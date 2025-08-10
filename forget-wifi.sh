#!/bin/bash
# Trennt aktuelles WLAN auf wlan0 und entfernt dessen Block aus wpa_supplicant.conf (eth0 unberührt).

IFACE="wlan0"
WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"

have(){ command -v "$1" >/dev/null 2>&1; }

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

# Guard: wlan bereit
rfkill unblock wifi 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true

SSID=$(iwgetid "$IFACE" -r 2>/dev/null)
[ -z "$SSID" ] && { echo "[!] Nicht mit einem WLAN verbunden (wlan0)."; exit 1; }

echo "[*] Trenne WLAN \"$SSID\" und entferne Zugangsdaten..."

# Disconnect + IP flush nur für wlan0
have wpa_cli && wpa_cli -i "$IFACE" disconnect >/dev/null 2>&1 || true
ip addr flush dev "$IFACE" 2>/dev/null || true

# Block aus Konfig entfernen
[ -f "$WPA_FILE" ] || { echo "[!] $WPA_FILE nicht gefunden."; exit 1; }
cp "$WPA_FILE" "${WPA_FILE}.bak.$(date +%s)"

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
}' "$WPA_FILE" > "${WPA_FILE}.tmp" && mv "${WPA_FILE}.tmp" "$WPA_FILE"

# wpa_supplicant reconfigure und DHCP auf wlan0 freigeben
systemctl start wpa_supplicant >/dev/null 2>&1 || systemctl start "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
have wpa_cli && wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true
have dhcpcd && dhcpcd -x "$IFACE" >/dev/null 2>&1 || true

WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] WLAN \"$SSID\" getrennt und vergessen."
echo "    WLAN-IP: ${WLAN_IP:- -}"
[ -n "$ETH_IP" ] && echo "    LAN-IP:  $ETH_IP"
