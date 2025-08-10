#!/bin/bash
# start-ap.sh
# Startet einen Access Point auf wlan0: SSID/PW = dmscreen / dmscreen
# Nutzt hostapd + dnsmasq (Snippet). eth0 bleibt unangetastet.

SSID="dmscreen"
PASS="dmscreen"
IFACE="wlan0"
AP_IP="192.168.4.1/24"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
DEFAULT_HOSTAPD="/etc/default/hostapd"

log(){ echo -e "$@"; }
need_root(){ [ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }; }
svc_active(){ systemctl is-active --quiet "$1"; }
have(){ command -v "$1" >/dev/null 2>&1; }

need_root

# Pakete vorhanden?
have hostapd || { echo "[!] hostapd fehlt. Installiere: sudo apt-get install -y hostapd"; exit 1; }
have dnsmasq || { echo "[!] dnsmasq fehlt. Installiere: sudo apt-get install -y dnsmasq"; exit 1; }

log "[*] Schalte in AP-Modus (SSID: ${SSID})..."

# WLAN-Client-Dienste für wlan0 stoppen (ohne eth0 zu berühren)
systemctl stop wpa_supplicant >/dev/null 2>&1 || systemctl stop "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
have dhcpcd && dhcpcd -x "$IFACE" >/dev/null 2>&1 || true

# wlan0 vorbereiten
ip addr flush dev "$IFACE" || true
ip link set "$IFACE" up || true
ip addr add "$AP_IP" dev "$IFACE"

# hostapd-Konfig schreiben
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

# /etc/default/hostapd so setzen, dass unser Config genutzt wird
if [ -f "$DEFAULT_HOSTAPD" ]; then
  if grep -q '^DAEMON_CONF=' "$DEFAULT_HOSTAPD"; then
    sed -i "s|^DAEMON_CONF=.*|DAEMON_CONF=\"$HOSTAPD_CONF\"|" "$DEFAULT_HOSTAPD"
  else
    echo "DAEMON_CONF=\"$HOSTAPD_CONF\"" >> "$DEFAULT_HOSTAPD"
  fi
fi

# dnsmasq-Snippet für wlan0 (anstatt /etc/dnsmasq.conf zu überschreiben)
cat > "$DNSMASQ_SNIPPET" <<EOF
interface=$IFACE
bind-interfaces
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
EOF

# dnsmasq neu laden/ starten
if svc_active dnsmasq; then
  systemctl reload dnsmasq || systemctl restart dnsmasq || true
else
  systemctl start dnsmasq || true
fi

# hostapd starten
systemctl unmask hostapd >/dev/null 2>&1 || true
systemctl start hostapd

# Statusausgabe
sleep 1
if svc_active hostapd; then
  ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)
  WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
  log "[+] AP aktiv. SSID: \"$SSID\"  Passwort: \"$PASS\""
  log "    AP-IP (wlan0): ${WLAN_IP:-192.168.4.1}"
  [ -n "$ETH_IP" ] && log "    LAN-IP (eth0, unverändert): ${ETH_IP}"
  exit 0
else
  log "[!] hostapd konnte nicht gestartet werden. Logs prüfen: journalctl -u hostapd -b"
  exit 2
fi
