#!/bin/bash
# forget-wifi.sh
# Trennt das aktuelle WLAN auf wlan0 und entfernt dessen network-Block aus wpa_supplicant.conf
# eth0 bleibt unangetastet.

WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"
IFACE="wlan0"

log(){ echo -e "$@"; }
need_root(){ [ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }; }
have(){ command -v "$1" >/dev/null 2>&1; }

need_root

SSID=$(iwgetid "$IFACE" -r 2>/dev/null)
if [ -z "$SSID" ]; then
  echo "[!] Nicht mit einem WLAN verbunden (wlan0)."
  exit 1
fi

echo "[*] Trenne WLAN \"$SSID\" und entferne Zugangsdaten aus ${WPA_FILE}"

# Trennen (nur wlan0)
if have wpa_cli; then wpa_cli -i "$IFACE" disconnect >/dev/null 2>&1 || true; fi
ip addr flush dev "$IFACE" || true

# Backup und Block entfernen
[ -f "$WPA_FILE" ] || { echo "[!] ${WPA_FILE} nicht gefunden."; exit 1; }
cp "$WPA_FILE" "${WPA_FILE}.bak.$(date +%s)"

awk -v ssid="$SSID" '
BEGIN{inblk=0}
{
  if($0 ~ /^network=\{/){inblk=1; buf=$0 ORS; next}
  if(inblk){
    buf=buf $0 ORS
    if($0 ~ /^\}/){
      if(buf ~ "ssid=\""ssid"\""){next} # Block verwerfen
      else{printf "%s", buf}
      inblk=0; buf=""
    }
    next
  }
  print
}' "$WPA_FILE" > "${WPA_FILE}.tmp" && mv "${WPA_FILE}.tmp" "$WPA_FILE"

# Neu laden
systemctl start wpa_supplicant >/dev/null 2>&1 || systemctl start "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
if have wpa_cli; then wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true; fi

# DHCP für wlan0 freigeben (ohne eth0 zu berühren)
have dhcpcd && dhcpcd -x "$IFACE" >/dev/null 2>&1 || true

WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] WLAN \"$SSID\" getrennt und vergessen."
[ -n "$WLAN_IP" ] && echo "    WLAN-IP: ${WLAN_IP}" || echo "    WLAN-IP: -"
[ -n "$ETH_IP" ] && echo "    LAN-IP:  ${ETH_IP}"
