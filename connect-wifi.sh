#!/bin/bash
# Nutzung: sudo ./connect-wifi.sh "SSID" "PASSWORT"
# Schaltet ggf. aus AP zurück, aktiviert Client-Betrieb auf wlan0 und holt DHCP (eth0 unberührt).

SSID="$1"
PASS="$2"
IFACE="wlan0"
WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
HOSTAPD_SVC="hostapd"

have(){ command -v "$1" >/dev/null 2>&1; }
svc_active(){ systemctl is-active --quiet "$1"; }

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }
[ -n "$SSID" ] && [ -n "$PASS" ] || { echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""; exit 1; }

echo "[*] Ziel: mit SSID \"$SSID\" verbinden (Client-Modus). Status wird ermittelt..."

# 0) AP sauber beenden (nur wlan0-bezogen)
systemctl stop "$HOSTAPD_SVC" >/dev/null 2>&1 || true
if [ -f "$DNSMASQ_SNIPPET" ]; then
  rm -f "$DNSMASQ_SNIPPET"
  if svc_active dnsmasq; then
    systemctl reload dnsmasq >/dev/null 2>&1 || systemctl restart dnsmasq >/dev/null 2>&1 || true
  fi
fi

# 1) WLAN entsperren & hochfahren, alte IPs weg
rfkill unblock wifi 2>/dev/null || true
ip link set "$IFACE" up 2>/dev/null || true
ip addr flush dev "$IFACE" 2>/dev/null || true

# 2) wpa_supplicant-Konfig aktualisieren (Header sicherstellen, SSID-Block ersetzen)
if [ -f "$WPA_FILE" ]; then
  cp "$WPA_FILE" "${WPA_FILE}.bak.$(date +%s)"
fi
mkdir -p "$(dirname "$WPA_FILE")"

# Header schreiben/erhalten
if ! grep -q '^ctrl_interface=' "$WPA_FILE" 2>/dev/null; then
  cat > "$WPA_FILE" <<'HDR'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE
HDR
fi

# SSID-Block ersetzen/hinzufügen
awk -v ssid="$SSID" -v pass="$PASS" '
BEGIN{inblk=0}
{
  if($0 ~ /^network=\{/){inblk=1; buf=$0 ORS; next}
  if(inblk){
    buf=buf $0 ORS
    if($0 ~ /^\}/){
      if(buf ~ "ssid=\""ssid"\""){next} else {printf "%s", buf}
      inblk=0; buf=""
    }
    next
  }
  print
}
END{
  print ""
  print "network={"
  print "    ssid=\""ssid"\""
  print "    psk=\""pass"\""
  print "}"
}' "$WPA_FILE" > "${WPA_FILE}.tmp" && mv "${WPA_FILE}.tmp" "$WPA_FILE"

# 3) wpa_supplicant für wlan0 starten/neu laden
systemctl start wpa_supplicant >/dev/null 2>&1 || systemctl start "wpa_supplicant@$IFACE" >/dev/null 2>&1 || true
have wpa_cli && wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true

# 4) DHCP für wlan0 nudgen
have dhcpcd && { dhcpcd -x "$IFACE" >/dev/null 2>&1 || true; dhcpcd -n "$IFACE" >/dev/null 2>&1 || true; }

# 5) Auf IP warten + letzter Fallback
for i in {1..10}; do
  WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
  [ -n "$WLAN_IP" ] && break
  sleep 1
done
if [ -z "$WLAN_IP" ]; then
  # letzter Notanker (optional, falls installiert)
  have dhclient && dhclient -v "$IFACE" || true
  sleep 2
  WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
fi

ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)

if [ -n "$WLAN_IP" ]; then
  echo "[+] Erfolgreich mit \"$SSID\" verbunden."
  echo "    WLAN-IP: $WLAN_IP"
  [ -n "$ETH_IP" ] && echo "    LAN-IP:  $ETH_IP"
  exit 0
else
  echo "[!] Keine WLAN-IP erhalten."
  [ -n "$ETH_IP" ] && echo "    LAN-IP (eth0, unverändert): $ETH_IP"
  exit 2
fi
