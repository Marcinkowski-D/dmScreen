#!/bin/bash
# start-ap.sh
# Startet einen WLAN-Access-Point mit SSID "dmscreen" und Passwort "dmscreen"

SSID="dmscreen"
PASS="dmscreen"
IFACE="wlan0"

# --- Root prüfen ---
if [ "$EUID" -ne 0 ]; then
    echo "Bitte mit sudo ausführen."
    exit 1
fi

# --- Pakete installieren (falls nicht vorhanden) ---
echo "[*] Prüfe Abhängigkeiten..."
apt-get update -y
apt-get install -y hostapd dnsmasq

# --- Hostapd konfigurieren ---
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
cat <<EOF > "$HOSTAPD_CONF"
interface=$IFACE
driver=nl80211
ssid=$SSID
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=$PASS
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

# hostapd auf diese Config verweisen
sed -i "s|#DAEMON_CONF=\"\"|DAEMON_CONF=\"$HOSTAPD_CONF\"|" /etc/default/hostapd

# --- dnsmasq konfigurieren ---
DNSMASQ_CONF="/etc/dnsmasq.conf"
# Backup anlegen, um doppelte Einträge zu vermeiden
if [ ! -f "${DNSMASQ_CONF}.bak" ]; then
    cp "$DNSMASQ_CONF" "${DNSMASQ_CONF}.bak"
fi
cat <<EOF > "$DNSMASQ_CONF"
interface=$IFACE
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
EOF

# --- wlan0 statische IP zuweisen ---
cat <<EOF > /etc/network/interfaces.d/$IFACE
auto $IFACE
iface $IFACE inet static
    address 192.168.4.1
    netmask 255.255.255.0
EOF

# --- Dienste starten ---
echo "[*] Starte Access Point..."
systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq
systemctl restart hostapd
systemctl restart dnsmasq

echo "[+] Access Point '$SSID' mit Passwort '$PASS' gestartet."
echo "[+] Netzwerk: 192.168.4.0/24, Gateway: 192.168.4.1"
