#!/bin/bash
# stop-ap.sh – beendet nur den AP auf wlan0 und räumt auf.
# Kein Auto-Connect, kein DHCP-Start. wlan0 bleibt DOWN und ohne IP.
# eth0 bleibt unberührt.

set -euo pipefail

IFACE="wlan0"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

echo "[*] Stoppe AP-Modus und räume auf (ohne Auto-Connect)..."

# 1) hostapd beenden (nicht deaktivieren, damit start-ap.sh später wieder starten kann)
systemctl stop hostapd >/dev/null 2>&1 || true

# 2) dnsmasq: nur unser Snippet entfernen und neu laden (globalen Dienst nicht hart stoppen)
if [ -f "$DNSMASQ_SNIPPET" ]; then
  rm -f "$DNSMASQ_SNIPPET"
  systemctl reload dnsmasq >/dev/null 2>&1 || systemctl restart dnsmasq >/dev/null 2>&1 || true
fi

# 3) DHCP-Client auf wlan0 beenden & Lease freigeben (falls aktiv)
dhclient -r "$IFACE" >/dev/null 2>&1 || true
pkill -f "dhclient.*$IFACE" >/dev/null 2>&1 || true

# 4) wpa_supplicant NICHT starten – im Gegenteil: sicherstellen, dass er nicht automatisch losfunkt
systemctl stop "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
systemctl stop wpa_supplicant >/dev/null 2>&1 || true

# 5) Interface aufräumen: IPs weg, Interface DOWN
ip addr flush dev "$IFACE" >/dev/null 2>&1 || true
ip link set "$IFACE" down >/dev/null 2>&1 || true

# 6) Status ausgeben (eth0 bleibt Diagnoseport)
WLAN_IP=$(ip -4 addr show "$IFACE" 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP=$(ip -4 addr show eth0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] AP gestoppt. wlan0 ist jetzt DOWN und ohne IP."
echo "    WLAN-IP (wlan0): ${WLAN_IP:--}"
[ -n "${ETH_IP:-}" ] && echo "    LAN-IP  (eth0):  $ETH_IP"

exit 0
