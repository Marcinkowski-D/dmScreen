#!/bin/bash
# connect-wifi.sh – verbindet wlan0 mit SSID/PW (Client-Modus)

SSID="$1"
PASS="$2"
PASS="$2"
IFACE="wlan0"
WPA_IF_FILE="/etc/wpa_supplicant/wpa_supplicant-${IFACE}.conf"

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
[ -n "$SSID" ] && [ -n "$PASS" ] || { echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""; exit 1; }

echo "[*] Ziel: mit SSID \"$SSID\" verbinden."

# AP sicher aus
systemctl stop hostapd >/dev/null 2>&1 || true

# dnsmasq Snippet entfernen und Service neu laden/stoppen
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
if [ -f "$DNSMASQ_SNIPPET" ]; then
  rm -f "$DNSMASQ_SNIPPET"
  echo "[*] dnsmasq Snippet entfernt, lade Service neu..."
  systemctl reload dnsmasq >/dev/null 2>&1 || systemctl restart dnsmasq >/dev/null 2>&1 || true
fi

# Sicherstellen, dass kein DHCP-Server mehr auf wlan0 läuft
pkill -f "dnsmasq.*wlan0" >/dev/null 2>&1 || true

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

if [ -n "$WLAN_IP" ]; then
  echo "[+] Erfolgreich. WLAN-IP: $WLAN_IP"
  
  # Sicherstellen, dass wlan0 eine funktionierende Default-Route hat
  # Prüfe ob bereits eine Default-Route über wlan0 existiert
  if ! ip route show default | grep -q "dev $IFACE"; then
    # Hole Gateway-Adresse aus der Routing-Tabelle oder DHCP-Lease
    # Versuche zuerst, Gateway aus den wlan0-spezifischen Routen zu extrahieren
    GATEWAY=$(ip route show dev "$IFACE" | grep -v "default" | awk '/proto (dhcp|kernel)/{print $1}' | head -n1 | cut -d/ -f1)
    
    if [ -n "$GATEWAY" ]; then
      # Berechne Gateway aus dem Subnetz (typischerweise .1 im Netzwerk)
      SUBNET=$(echo "$GATEWAY" | cut -d. -f1-3)
      GATEWAY="${SUBNET}.1"
    else
      # Fallback: Verwende .1 basierend auf der wlan0 IP
      SUBNET=$(echo "$WLAN_IP" | cut -d. -f1-3)
      GATEWAY="${SUBNET}.1"
    fi
    
    echo "[*] Setze Default-Route über Gateway $GATEWAY dev $IFACE mit Metric 600..."
    ip route add default via "$GATEWAY" dev "$IFACE" metric 600 2>/dev/null || {
      echo "[!] Warnung: Konnte keine Default-Route hinzufügen (möglicherweise existiert bereits eine)"
    }
  else
    echo "[*] Default-Route über $IFACE bereits vorhanden."
  fi
  
  # Zeige finale Routing-Tabelle für Debugging
  echo "[*] Aktuelle Default-Routen:"
  ip route show default
else
  echo "[!] Keine IPv4 via DHCP erhalten."
fi
