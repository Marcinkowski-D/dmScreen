#!/bin/bash
# Startet AP auf wlan0 (SSID/PW: dmscreen/dmscreen) via hostapd + dnsmasq-Snippet. eth0 bleibt unberührt.

SSID="dmscreen"
PASS="dmscreen"
IFACE="wlan0"
AP_IP_CIDR="192.168.4.1/24"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
DEFAULT_HOSTAPD="/etc/default/hostapd"

have(){ command -v "$1" >/dev/null 2>&1; }
svc_active(){ systemctl is-active --quiet "$1"; }

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
have hostapd || { echo "[!] hostapd fehlt. Installiere: sudo apt-get install -y hostapd"; exit 1; }
have dnsmasq || { echo "[!] dnsmasq fehlt. Installiere: sudo apt-get install -y dnsmasq"; exit 1; }

echo "[*] Starte AP \"$SSID\" ..."

# Client-Dienste auf wlan0 stoppen
systemctl stop wpa_supplicant >/dev/null 2>&1 || systemctl stop "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
have dhcpcd && dhcpcd -x "$IFACE" >/dev/null 2>&1 || true

# WLAN entsperren, hochfahren, IP setzen
rfkill unblock wifi 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
ip addr add "$AP_IP_CIDR" dev "$IFACE"

# hostapd.conf schreiben
mkdir -p "$(dirname "$HOSTAPD_CONF")"
cat > "$HOSTAPD_CONF" <<EOF
interface=$IFACE
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$PASS
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
country_code=DE
EOF

# hostapd default-config Zeiger setzen
if [ -f "$DEFAULT_HOSTAPD" ]; then
  if grep -q '^DAEMON_CONF=' "$DEFAULT_HOSTAPD"; then
    sed -i "s|^DAEMON_CONF=.*|DAEMON_CONF=\"$HOSTAPD_CONF\"|" "$DEFAULT_HOSTAPD"
  else
    echo "DAEMON_CONF=\"$HOSTAPD_CONF\"" >> "$DEFAULT_HOSTAPD"
  fi
fi

# dnsmasq-Snippet (anstatt globale dnsmasq.conf)
cat > "$DNSMASQ_SNIPPET" <<EOF
interface=$IFACE
bind-interfaces
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
EOF

# dnsmasq reload/start
if svc_active dnsmasq; then
  systemctl reload dnsmasq >/dev/null 2>&1 || systemctl restart dnsmasq >/dev/null 2>&1 || true
else
  systemctl start dnsmasq >/dev/null 2>&1 || true
fi

# hostapd starten
systemctl unmask hostapd >/dev/null 2>&1 || true
systemctl start hostapd

sleep 1
if svc_active hostapd; then
  WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
  ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)
  echo "[+] AP aktiv. SSID: \"$SSID\"  Passwort: \"$PASS\""
  echo "    AP-IP (wlan0): ${WLAN_IP:-192.168.4.1}"
  [ -n "$ETH_IP" ] && echo "    LAN-IP (eth0, unverändert): $ETH_IP"
else
  echo "[!] hostapd konnte nicht gestartet werden. Logs: journalctl -u hostapd -b"
  exit 2
fi
