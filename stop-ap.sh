#!/bin/bash
# Stoppt AP auf wlan0 und stellt Client-Betrieb wieder her (eth0 unberührt).

IFACE="wlan0"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"

have(){ command -v "$1" >/dev/null 2>&1; }
svc_active(){ systemctl is-active --quiet "$1"; }

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

echo "[*] Stoppe AP-Modus und stelle Client-Betrieb auf wlan0 her..."

# hostapd stoppen
systemctl stop hostapd >/dev/null 2>&1 || true

# dnsmasq-Snippet entfernen und dnsmasq reloaden
if [ -f "$DNSMASQ_SNIPPET" ]; then
  rm -f "$DNSMASQ_SNIPPET"
  if svc_active dnsmasq; then
    systemctl reload dnsmasq >/dev/null 2>&1 || systemctl restart dnsmasq >/dev/null 2>&1 || true
  fi
fi

# wlan0 reinigen & hochfahren
rfkill unblock wifi 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
ip link set "$IFACE" down 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true

# wpa_supplicant wieder aktivieren und Konfig neu laden
systemctl start wpa_supplicant >/dev/null 2>&1 || systemctl start "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
have wpa_cli && wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true

# DHCP für wlan0 nudgen (+ letzter Fallback)
have dhcpcd && { dhcpcd -x "$IFACE" >/dev/null 2>&1 || true; dhcpcd -n "$IFACE" >/dev/null 2>&1 || true; }
sleep 2
WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
if [ -z "$WLAN_IP" ] && have dhclient; then
  dhclient -v "$IFACE" || true
  sleep 2
  WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
fi

ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] AP gestoppt. Clientmodus wieder aktiv."
echo "    WLAN-IP: ${WLAN_IP:- -}"
[ -n "$ETH_IP" ] && echo "    LAN-IP:  $ETH_IP"
