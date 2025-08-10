#!/bin/bash
# wifi-status.sh
# Zeigt kompakten Status für wlan0/eth0, erkennt AP/Client-Modus und typische Konflikte.
# Nutzung:
#   sudo ./wifi-status.sh          # ausführlich
#   sudo ./wifi-status.sh --brief  # kompakt

BRIEF=0
[ "$1" = "--brief" ] && BRIEF=1

IF_WLAN="wlan0"
IF_ETH="eth0"
WPA_FILE="/etc/wpa_supplicant/wpa_supplicant.conf"
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
DEFAULT_HOSTAPD="/etc/default/hostapd"
DNSMASQ_SNIPPET="/etc/dnsmasq.d/dmscreen.conf"
IF_STUB="/etc/network/interfaces.d/${IF_WLAN}"

have(){ command -v "$1" >/dev/null 2>&1; }
svc_active(){ systemctl is-active --quiet "$1"; }

hdr(){ echo -e "\n=== $1 ==="; }
kv(){ printf "  %-22s %s\n" "$1" "$2"; }

# --- Abschnitt: Interfaces & IPs ---
hdr "Interfaces & IPs"
WLAN_LINK=$(ip -o link show "$IF_WLAN" 2>/dev/null | sed 's/^[0-9]*: //')
ETH_LINK=$(ip -o link show "$IF_ETH" 2>/dev/null | sed 's/^[0-9]*: //')
WLAN_MAC=$(ip link show "$IF_WLAN" 2>/dev/null | awk '/link\/ether/{print $2}')
ETH_MAC=$(ip link show "$IF_ETH" 2>/dev/null | awk '/link\/ether/{print $2}')
WLAN_IP4=$(ip -4 addr show "$IF_WLAN" 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1)
ETH_IP4=$(ip -4 addr show "$IF_ETH" 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1)
kv "wlan0 link" "${WLAN_LINK:-(nicht vorhanden)}"
kv "wlan0 MAC"  "${WLAN_MAC:--}"
kv "wlan0 IPv4" "${WLAN_IP4:--}"
kv "eth0 link"  "${ETH_LINK:-(nicht vorhanden)}"
kv "eth0 MAC"   "${ETH_MAC:--}"
kv "eth0 IPv4"  "${ETH_IP4:--}"

# --- Abschnitt: RF & Reg ---
hdr "RF & Regulatorik"
RFK=$(rfkill list 2>/dev/null | sed 's/^/  /' || true)
echo "${RFK:-  rfkill nicht verfügbar}"
if have iw; then
  kv "Reg-Domain" "$(iw reg get 2>/dev/null | awk '/country/{print $2}' | head -n1)"
fi

# --- Abschnitt: WLAN-Verbindung ---
hdr "WLAN-Verbindung"
if have iw; then
  IWLINK=$(iw "$IF_WLAN" link 2>/dev/null)
  if echo "$IWLINK" | grep -q "^Connected"; then
    SSID=$(echo "$IWLINK" | awk -F': ' '/SSID:/{print $2}')
    kv "Status" "Verbunden"
    kv "SSID"   "${SSID:--}"
  else
    kv "Status" "Nicht verbunden"
    [ $BRIEF -eq 0 ] && echo "$IWLINK" | sed 's/^/  /'
  fi
else
  kv "iw" "nicht installiert"
fi

# --- Abschnitt: Services ---
hdr "Services"
for SVC in wpa_supplicant "wpa_supplicant@$IF_WLAN" hostapd dnsmasq dhcpcd; do
  if systemctl list-unit-files | grep -q "^$SVC"; then
    STATE=$(systemctl is-active "$SVC" 2>/dev/null || true)
    ENAB=$(systemctl is-enabled "$SVC" 2>/dev/null || true)
    kv "$SVC" "$STATE (enabled: $ENAB)"
  fi
done

# --- Abschnitt: Routing ---
hdr "Routing"
DEFRT=$(ip route | awk '/^default/{print $0}')
[ -n "$DEFRT" ] && kv "Default-Route" "$DEFRT" || kv "Default-Route" "(keine)"
[ $BRIEF -eq 0 ] && ip route | sed 's/^/  /'

# --- Abschnitt: Konfig-Checks ---
hdr "Konfig-Checks"
[ -f "$WPA_FILE" ] && kv "wpa_supplicant.conf" "$WPA_FILE" || kv "wpa_supplicant.conf" "(fehlt)"
[ -f "$HOSTAPD_CONF" ] && kv "hostapd.conf" "$HOSTAPD_CONF" || kv "hostapd.conf" "(fehlt)"
if [ -f "$DEFAULT_HOSTAPD" ]; then
  DAEMON_CONF=$(grep -E '^DAEMON_CONF=' "$DEFAULT_HOSTAPD" 2>/dev/null | cut -d= -f2- | tr -d '"')
  kv "/etc/default/hostapd" "DAEMON_CONF=${DAEMON_CONF:-(unset)}"
fi
[ -f "$DNSMASQ_SNIPPET" ] && kv "dnsmasq snippet" "$DNSMASQ_SNIPPET (AKTIV)" || kv "dnsmasq snippet" "(nicht aktiv)"
[ -f "$IF_STUB" ] && kv "interfaces.d/wlan0" "$IF_STUB (Achtung: statisch?)" || kv "interfaces.d/wlan0" "(nicht vorhanden)"
if [ -f /etc/dhcpcd.conf ]; then
  if grep -q "denyinterfaces.*$IF_WLAN" /etc/dhcpcd.conf; then
    kv "dhcpcd.conf" "WARN: denyinterfaces $IF_WLAN gesetzt"
  else
    kv "dhcpcd.conf" "ok"
  fi
fi

# --- Abschnitt: Modus-Erkennung & Konflikte ---
hdr "Modus & Konflikte"
AP_ACTIVE=0; CLI_ACTIVE=0
svc_active hostapd && AP_ACTIVE=1
if have iw && iw "$IF_WLAN" link 2>/dev/null | grep -q "^Connected"; then
  CLI_ACTIVE=1
fi

if [ $AP_ACTIVE -eq 1 ] && [ $CLI_ACTIVE -eq 1 ]; then
  kv "Modus" "KONFLIKT: AP und Client gleichzeitig aktiv"
elif [ $AP_ACTIVE -eq 1 ]; then
  kv "Modus" "AP"
elif [ $CLI_ACTIVE -eq 1 ]; then
  kv "Modus" "Client"
else
  kv "Modus" "Keiner (idle)"
fi

# Typische Stolpersteine melden
if [ -f "$IF_STUB" ]; then
  echo "  Hinweis: $IF_STUB vorhanden – kann DHCP auf wlan0 verhindern."
fi
if [ $AP_ACTIVE -eq 1 ] && [ -z "$WLAN_IP4" ]; then
  echo "  Hinweis: AP aktiv, aber keine 192.168.4.1 gesetzt? (ip addr add prüfen)"
fi
if [ $CLI_ACTIVE -eq 1 ] && [ -z "$WLAN_IP4" ]; then
  echo "  Hinweis: mit WLAN verbunden, aber keine IPv4 – DHCP anstoßen: 'dhcpcd -n $IF_WLAN'"
fi
if [ -n "$DNSMASQ_SNIPPET" ] && [ -f "$DNSMASQ_SNIPPET" ] && [ $CLI_ACTIVE -eq 1 ]; then
  echo "  Hinweis: dnsmasq-Snippet aktiv während Client-Modus – besser entfernen."
fi

# --- Ende ---
[ $BRIEF -eq 1 ] && exit 0

# Zusatzdetails (nur ausführlich): wpa_supplicant & Logschnipsel
if have wpa_cli; then
  hdr "wpa_cli status ($IF_WLAN)"
  wpa_cli -i "$IF_WLAN" status 2>/dev/null | sed 's/^/  /' || echo "  (kein wpa_cli oder kein Socket)"
fi

hdr "Letzte hostapd/dnsmasq Events (optional)"
journalctl -u hostapd -n 20 -q 2>/dev/null | sed 's/^/  /' || true
journalctl -u dnsmasq -n 20 -q 2>/dev/null | sed 's/^/  /' || true
