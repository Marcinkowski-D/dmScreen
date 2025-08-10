#!/bin/bash
# connect-wifi.sh – verbindet wlan0 mit SSID/PW (Client-Modus, eth0 bleibt unberührt)

SSID="$1"
PASS="$2"
IFACE="wlan0"
WPA_IF_FILE="/etc/wpa_supplicant/wpa_supplicant-${IFACE}.conf"

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
[ -n "$SSID" ] && [ -n "$PASS" ] || { echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""; exit 1; }

echo "[*] Ziel: mit SSID \"$SSID\" verbinden."

# AP sicher aus
systemctl stop hostapd >/dev/null 2>&1 || true

# WLAN bereit machen
rfkill unblock wifi 2>/dev/null || true
ip link set "$IFACE" down 2>/dev/null || true
modprobe -r brcmfmac brcmutil 2>/dev/null || true
modprobe brcmfmac 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true
iw reg set DE 2>/dev/null || true

# dhcpcd soll wlan0 NICHT anfassen (Konflikte mit dhclient vermeiden)
grep -q '^denyinterfaces .*wlan0' /etc/dhcpcd.conf 2>/dev/null || {
  echo "denyinterfaces wlan0" >> /etc/dhcpcd.conf
  systemctl daemon-reload 2>/dev/null || true
  systemctl restart dhcpcd 2>/dev/null || true
}

# wpa_supplicant Config schreiben
[ -f "$WPA_IF_FILE" ] && cp "$WPA_IF_FILE" "${WPA_IF_FILE}.bak.$(date +%s)"
cat > "$WPA_IF_FILE" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE

network={
    ssid="$SSID"
    psk="$PASS"
    scan_ssid=1
    # Nur 2,4 GHz erzwingen? -> nächste Zeile entkommentieren:
    # freq_list=2412 2437 2462
}
EOF
chmod 600 "$WPA_IF_FILE"

# wpa_supplicant@wlan0 sauber starten
systemctl stop wpa_supplicant >/dev/null 2>&1 || true
systemctl daemon-reload 2>/dev/null || true
systemctl enable --now "wpa_supplicant@${IFACE}" >/dev/null 2>&1 || systemctl start "wpa_supplicant@${IFACE}"
wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true
wpa_cli -i "$IFACE" enable_network all >/dev/null 2>&1 || true

# Auf Association warten
echo "[*] Warte auf Association..."
ok=0
for _ in {1..20}; do
  state=$(wpa_cli -i "$IFACE" status 2>/dev/null | awk -F= '/^wpa_state=/{print $2}')
  if [ "$state" = "COMPLETED" ]; then ok=1; break; fi
  sleep 1
done
if [ "$ok" -ne 1 ]; then
  echo "[!] Keine erfolgreiche Assoziation. Status:"
  wpa_cli -i "$IFACE" status 2>/dev/null || true
  exit 2
fi
echo "[+] Assoziiert mit \"$SSID\"."

# DHCP nur für wlan0 via dhclient
pkill -f "dhclient.*$IFACE" >/dev/null 2>&1 || true
if ! command -v dhclient >/dev/null 2>&1; then
  echo "[!] dhclient fehlt. Installiere: sudo apt-get install -y isc-dhcp-client"
  exit 3
fi
dhclient -v -1 "$IFACE" || true

WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

if [ -n "$WLAN_IP" ]; then
  echo "[+] Erfolgreich. WLAN-IP: $WLAN_IP"
else
  echo "[!] Keine IPv4 via DHCP erhalten."
fi
[ -n "$ETH_IP" ] && echo "    LAN-IP (eth0): $ETH_IP"
