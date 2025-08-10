#!/bin/bash
# connect-wifi.sh
# Nutzung: sudo ./connect-wifi.sh "SSID" "PASSWORT"
# Schaltet ggf. aus AP-Modus zurück, startet wpa_supplicant und holt DHCP NUR für wlan0.
# eth0 bleibt komplett unangetastet.

SSID="$1"
PASS="$2"
WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
IFACE="wlan0"

log(){ echo -e "$@"; }
need_root(){ [ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }; }
svc_active(){ systemctl is-active --quiet "$1"; }
have(){ command -v "$1" >/dev/null 2>&1; }

start_wpa(){
  if svc_active wpa_supplicant; then
    systemctl restart wpa_supplicant
  else
    systemctl start wpa_supplicant || systemctl start "wpa_supplicant@$IFACE" || true
  fi
}

kick_dhcpcd_wlan(){
  have dhcpcd && { dhcpcd -x "$IFACE" >/dev/null 2>&1 || true; dhcpcd -n "$IFACE" >/dev/null 2>&1 || true; }
}

wait_ip(){
  for i in {1..20}; do
    WLAN_IP=$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1)
    [ -n "$WLAN_IP" ] && return 0
    sleep 1
  done
  return 1
}

# --- main ---
need_root
[ -z "$SSID" ] && { echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""; exit 1; }
[ -z "$PASS" ] && { echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""; exit 1; }

log "[*] Ziel: mit SSID \"$SSID\" verbinden (Client-Modus). Status wird ermittelt..."

# Falls AP läuft: sauber abschalten, aber eth0 unberührt
if svc_active hostapd; then
  log "    - hostapd ist aktiv -> stoppe AP..."
  systemctl stop hostapd || true
fi

# dnsmasq: nur unser Snippet entfernen, Service neu laden (kein harter Stop nötig)
if [ -f "$DNSMASQ_SNIPPET" ]; then
  log "    - Entferne dnsmasq-Snippet $DNSMASQ_SNIPPET und reloade dnsmasq"
  rm -f "$DNSMASQ_SNIPPET"
  if svc_active dnsmasq; then
    systemctl reload dnsmasq || systemctl restart dnsmasq || true
  fi
fi

# Sicherstellen, dass wlan0 „clean“ ist (keine alte statische AP-IP)
ip addr flush dev "$IFACE" || true
ip link set "$IFACE" up || true

# wpa_supplicant-Konfig aktualisieren (ohne eth0 anzufassen)
if [ -f "$WPA_FILE" ]; then
  cp "$WPA_FILE" "${WPA_FILE}.bak.$(date +%s)"
else
  mkdir -p "$(dirname "$WPA_FILE")"
fi

# Header sicherstellen
grep -q '^ctrl_interface=' "$WPA_FILE" 2>/dev/null || {
  cat <<'HDR' > "$WPA_FILE"
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=DE
HDR
}

# Netzwerkblock für SSID hinzufügen/ersetzen
awk -v ssid="$SSID" -v pass="$PASS" '
BEGIN{inblk=0}
{
  if($0 ~ /^network=\{/){inblk=1; buf=$0 ORS; next}
  if(inblk){
    buf=buf $0 ORS
    if($0 ~ /^\}/){
      if(buf ~ "ssid=\""ssid"\""){next} # ganzen Block verwerfen
      else{printf "%s", buf}
      inblk=0; buf=""
    }
    next
  }
  print
}
END{
  # neuen Block anhängen
  print ""
  print "network={"
  print "    ssid=\""ssid"\""
  print "    psk=\""pass"\""
  print "}"
}' "$WPA_FILE" > "${WPA_FILE}.tmp" && mv "${WPA_FILE}.tmp" "$WPA_FILE"

# wpa_supplicant starten/neu laden (nur für wlan0 relevant)
start_wpa
# Neu verbinden
if have wpa_cli; then wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true; fi

# DHCP nur für wlan0 anstoßen
kick_dhcpcd_wlan

# Auf IP warten
if wait_ip; then
  ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)
  log "[+] Erfolgreich mit \"$SSID\" verbunden."
  log "    WLAN-IP: ${WLAN_IP}"
  [ -n "$ETH_IP" ] && log "    LAN-IP:  ${ETH_IP}"
  exit 0
else
  ETH_IP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)
  log "[!] Keine WLAN-IP erhalten (SSID/PW ok?)."
  [ -n "$ETH_IP" ] && log "    LAN-IP (eth0, unverändert): ${ETH_IP}"
  exit 2
fi
