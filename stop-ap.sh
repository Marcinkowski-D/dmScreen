#!/bin/bash
# stop-ap.sh – stoppt AP auf wlan0 und stellt Client-Betrieb wieder her (eth0 bleibt unberührt)

IFACE="wlan0"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
WPA_IF_FILE="/etc/wpa_supplicant/wpa_supplicant-${IFACE}.conf"

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

echo "[*] Stoppe AP-Modus und stelle Client-Modus wieder her..."

# AP stoppen
systemctl stop hostapd >/dev/null 2>&1 || true

# dnsmasq-Snippet entfernen + reload
if [ -f "$DNSMASQ_SNIPPET" ]; then
  rm -f "$DNSMASQ_SNIPPET"
  systemctl reload dnsmasq >/dev/null 2>&1 || systemctl restart dnsmasq >/dev/null 2>&1 || true
fi

# wlan0 reinigen & hochfahren
rfkill unblock wifi 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
ip link set "$IFACE" down 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true

# wpa_supplicant@wlan0 starten + reconfigure
systemctl stop wpa_supplicant >/dev/null 2>&1 || true
systemctl enable --now "wpa_supplicant@${IFACE}" >/dev/null 2>&1 || systemctl start "wpa_supplicant@${IFACE}"
wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true
wpa_cli -i "$IFACE" enable_network all >/dev/null 2>&1 || true

# Optional: falls Netz(e) vorhanden, kurz versuchen zu verbinden und DHCP holen
if [ -s "$WPA_IF_FILE" ]; then
  # Warte kurz auf Association
  for _ in {1..8}; do
    state=$(wpa_cli -i "$IFACE" status 2>/dev/null | awk -F= '/^wpa_state=/{print $2}')
    [ "$state" = "COMPLETED" ] && break
    sleep 1
  done
  # DHCP via dhclient (nur wlan0)
  pkill -f "dhclient.*$IFACE" >/dev/null 2>&1 || true
  command -v dhclient >/dev/null 2>&1 && dhclient -v -1 "$IFACE" || true
fi

WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] AP gestoppt. Clientmodus wieder aktiv."
echo "    WLAN-IP: ${WLAN_IP:- -}"
[ -n "$ETH_IP" ] && echo "    LAN-IP (eth0): $ETH_IP"
