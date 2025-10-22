#!/bin/bash
# wifi-check.sh
# Zeigt kompakten Status für wlan0 via nmcli (NetworkManager)
# Nutzung:
#   sudo ./wifi-check.sh          # ausführlich
#   sudo ./wifi-check.sh --brief  # kompakt

BRIEF=0
[ "$1" = "--brief" ] && BRIEF=1

IF_WLAN="wlan0"

have(){ command -v "$1" >/dev/null 2>&1; }
svc_active(){ systemctl is-active --quiet "$1"; }

hdr(){ echo -e "\n=== $1 ==="; }
kv(){ printf "  %-22s %s\n" "$1" "$2"; }

# Prüfe ob nmcli verfügbar ist
if ! have nmcli; then
    echo "[!] nmcli nicht gefunden. Bitte NetworkManager installieren:"
    echo "    sudo apt-get install -y network-manager"
    exit 1
fi

# --- Abschnitt: NetworkManager Status ---
hdr "NetworkManager Status"
if svc_active NetworkManager; then
    kv "NetworkManager" "aktiv"
    NM_VERSION=$(nmcli --version | head -n1)
    kv "Version" "$NM_VERSION"
else
    kv "NetworkManager" "INAKTIV oder nicht installiert"
    echo "[!] NetworkManager muss laufen für nmcli-basierte Netzwerkverwaltung"
    exit 1
fi

# --- Abschnitt: Interfaces & IPs ---
hdr "Interfaces & IPs"
WLAN_LINK=$(ip -o link show "$IF_WLAN" 2>/dev/null | sed 's/^[0-9]*: //')
WLAN_MAC=$(ip link show "$IF_WLAN" 2>/dev/null | awk '/link\/ether/{print $2}')
WLAN_IP4=$(nmcli -t -f IP4.ADDRESS dev show "$IF_WLAN" 2>/dev/null | grep 'IP4.ADDRESS' | cut -d: -f2 | cut -d/ -f1 | head -n1)
WLAN_STATE=$(nmcli -t -f DEVICE,STATE dev status | grep "^$IF_WLAN:" | cut -d: -f2)

kv "wlan0 link" "${WLAN_LINK:-(nicht vorhanden)}"
kv "wlan0 MAC"  "${WLAN_MAC:--}"
kv "wlan0 State" "${WLAN_STATE:--}"
kv "wlan0 IPv4" "${WLAN_IP4:--}"

# --- Abschnitt: RF & Reg ---
hdr "RF & Regulatorik"
RFK=$(rfkill list 2>/dev/null | sed 's/^/  /' || true)
echo "${RFK:-  rfkill nicht verfügbar}"
if have iw; then
  kv "Reg-Domain" "$(iw reg get 2>/dev/null | awk '/country/{print $2}' | head -n1)"
fi

# --- Abschnitt: WLAN-Verbindung ---
hdr "WLAN-Verbindung (nmcli)"
# Hole aktive SSID
ACTIVE_SSID=$(nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes:' | cut -d: -f2)
ACTIVE_CONN=$(nmcli -t -f NAME,TYPE,DEVICE connection show --active | grep ":802-11-wireless:$IF_WLAN$" | cut -d: -f1)

if [ -n "$ACTIVE_SSID" ]; then
    kv "Status" "Verbunden"
    kv "SSID" "$ACTIVE_SSID"
    kv "Connection" "${ACTIVE_CONN:-$ACTIVE_SSID}"
    
    # Zeige Signal-Stärke
    SIGNAL=$(nmcli -t -f ACTIVE,SIGNAL dev wifi | grep '^yes:' | cut -d: -f2)
    [ -n "$SIGNAL" ] && kv "Signal" "$SIGNAL%"
    
    # Zeige WiFi-Details wenn verfügbar
    if have iw; then
        FREQ=$(iw "$IF_WLAN" link 2>/dev/null | awk '/freq:/{print $2}')
        [ -n "$FREQ" ] && kv "Frequenz" "${FREQ} MHz"
    fi
else
    # Prüfe ob Hotspot aktiv ist
    HOTSPOT_CONN=$(nmcli -t -f NAME,TYPE connection show --active | grep 'Hotspot:802-11-wireless' | cut -d: -f1)
    if [ -n "$HOTSPOT_CONN" ]; then
        kv "Status" "Hotspot aktiv"
        kv "Connection" "$HOTSPOT_CONN"
        # Hole Hotspot-SSID
        HOTSPOT_SSID=$(nmcli -t -f 802-11-wireless.ssid connection show "$HOTSPOT_CONN" 2>/dev/null | cut -d: -f2)
        [ -n "$HOTSPOT_SSID" ] && kv "SSID" "$HOTSPOT_SSID"
    else
        kv "Status" "Nicht verbunden"
    fi
fi

# --- Abschnitt: Gespeicherte Verbindungen ---
hdr "Gespeicherte WiFi-Verbindungen"
SAVED_CONNS=$(nmcli -t -f NAME,TYPE connection show | grep ':802-11-wireless$' | cut -d: -f1)
if [ -n "$SAVED_CONNS" ]; then
    echo "$SAVED_CONNS" | while read -r conn; do
        kv "→" "$conn"
    done
else
    echo "  (keine gespeicherten Verbindungen)"
fi

# --- Abschnitt: Routing ---
hdr "Routing"
DEFRT=$(ip route | awk '/^default/{print $0}')
[ -n "$DEFRT" ] && kv "Default-Route" "$DEFRT" || kv "Default-Route" "(keine)"
if [ $BRIEF -eq 0 ]; then
    echo "  Alle Routen:"
    ip route | sed 's/^/    /'
fi

# --- Abschnitt: Sichtbare WLANs ---
if [ $BRIEF -eq 0 ]; then
    hdr "Sichtbare WLANs (Scan)"
    echo "  Scanne..."
    nmcli device wifi rescan 2>/dev/null || true
    sleep 1
    nmcli -t -f SSID,SIGNAL,SECURITY device wifi list 2>/dev/null | head -n 10 | while IFS=: read -r ssid signal security; do
        [ -z "$ssid" ] || [ "$ssid" = "--" ] && continue
        printf "  %-30s %3s%%  %s\n" "$ssid" "$signal" "$security"
    done
fi

# --- Abschnitt: Modus-Erkennung ---
hdr "Modus & Status"
AP_ACTIVE=0; CLI_ACTIVE=0

# Prüfe ob Hotspot aktiv
nmcli -t -f NAME,TYPE connection show --active | grep -q 'Hotspot:802-11-wireless' && AP_ACTIVE=1

# Prüfe ob als Client verbunden
[ -n "$ACTIVE_SSID" ] && CLI_ACTIVE=1

if [ $AP_ACTIVE -eq 1 ] && [ $CLI_ACTIVE -eq 1 ]; then
    kv "Modus" "KONFLIKT: AP und Client gleichzeitig aktiv (sollte nicht vorkommen)"
elif [ $AP_ACTIVE -eq 1 ]; then
    kv "Modus" "AP (Hotspot)"
elif [ $CLI_ACTIVE -eq 1 ]; then
    kv "Modus" "Client (verbunden mit WLAN)"
else
    kv "Modus" "Idle (nicht verbunden)"
fi

# Zusätzliche Hinweise
if [ $CLI_ACTIVE -eq 1 ] && [ -z "$WLAN_IP4" ]; then
    echo "  [!] Mit WLAN verbunden, aber keine IPv4-Adresse (DHCP-Problem?)"
fi

# --- Ende ---
[ $BRIEF -eq 1 ] && exit 0

# --- Zusatzdetails (nur ausführlich) ---
hdr "NetworkManager Details"
echo "  Alle Geräte:"
nmcli device status | sed 's/^/    /'

echo ""
echo "  Alle Verbindungen:"
nmcli connection show | sed 's/^/    /'

hdr "NetworkManager Logs (letzte 20 Zeilen)"
journalctl -u NetworkManager -n 20 -q --no-pager 2>/dev/null | sed 's/^/  /' || echo "  (journalctl nicht verfügbar)"

exit 0
