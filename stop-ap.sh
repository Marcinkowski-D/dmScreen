#!/bin/bash
# stop-ap.sh
# Beendet den AP-Modus auf wlan0 und stellt Client-Betrieb wieder her (ohne eth0 zu verändern)

IFACE="wlan0"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"

log(){ echo -e "$@"; }
need_root(){ [ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }; }
svc_active(){ systemctl is-active --quiet "$1"; }
have(){ command -v "$1" >/dev/null 2>&1; }

need_root
log "[*] Stoppe AP-Modus und stelle Client-Betrieb wieder her..."

# hostapd stoppen
systemctl stop hostapd >/dev/null 2>&1 || true

# dnsmasq-Snippet entfernen und Service reloaden (globaler Stop nicht nötig)
if [ -f "$DNSMASQ_SNIPPET" ]; then
  rm -f "$DNSMASQ_SNIPPET"
  if svc_active dnsmasq; then
    systemctl reload dnsmasq || systemctl restart dnsmasq || true
  fi
fi

# wlan0 IP aufräumen
ip addr flush dev "$IFACE" || true
ip link set "$IFACE" down || true
ip link set "$IFACE" up || true

# wpa_supplicant für Clientbetrieb sicherstellen
systemctl start wpa_supplicant >/dev/null 2>&1 || systemctl start "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
if have wpa_cli; then wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true; fi

# DHCP nur für wlan0 triggern (eth0 unberührt)
have dhcpcd && { dhcpcd -x "$IFACE" >/dev/null 2>&1 || true; dhcpcd -n "$IFACE" >/dev/null 2>&1 || true; }

# Status
sleep 2
WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

echo "[+] AP gestoppt. Clientmodus wieder aktiv."
echo "    WLAN-IP: ${WLAN_IP:- -}"
[ -n "$ETH_IP" ] && echo "    LAN-IP:  ${ETH_IP}"
