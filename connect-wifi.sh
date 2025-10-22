#!/bin/bash
# connect-wifi.sh – verbindet wlan0 mit SSID/PW via nmcli (NetworkManager)
# Verwendung: sudo ./connect-wifi.sh "SSID" "PASSWORT"

SSID="$1"
PASS="$2"
IFACE="wlan0"

set -o pipefail

# Root-Check
[ "$EUID" -eq 0 ] || { echo "[!] Bitte mit sudo ausführen."; exit 1; }

# Parameter-Check
[ -n "$SSID" ] && [ -n "$PASS" ] || { 
    echo "Nutzung: sudo $0 \"SSID\" \"PASSWORT\""; 
    exit 1; 
}

# nmcli verfügbar?
if ! command -v nmcli >/dev/null 2>&1; then
    echo "[!] nmcli nicht gefunden. Bitte NetworkManager installieren:"
    echo "    sudo apt-get install -y network-manager"
    exit 1
fi

echo "[*] Ziel: mit SSID \"$SSID\" verbinden."

# AP sicher aus (Hotspot löschen)
echo "[*] Stoppe eventuell laufenden Hotspot..."
nmcli connection delete Hotspot >/dev/null 2>&1 || true

# Prüfe ob Verbindung bereits existiert
EXISTING_CONN=$(nmcli -t -f NAME connection show | grep "^$SSID$")

if [ -n "$EXISTING_CONN" ]; then
    echo "[*] Verbindung \"$SSID\" existiert bereits, versuche Aktivierung..."
    if nmcli connection up "$SSID"; then
        echo "[+] Erfolgreich mit \"$SSID\" verbunden (existierende Verbindung aktiviert)."
    else
        echo "[*] Aktivierung fehlgeschlagen, versuche erneute Verbindung..."
        # Lösche alte Verbindung und erstelle neu
        nmcli connection delete "$SSID" >/dev/null 2>&1 || true
        if nmcli device wifi connect "$SSID" password "$PASS" ifname "$IFACE"; then
            echo "[+] Erfolgreich mit \"$SSID\" verbunden (Verbindung neu erstellt)."
        else
            echo "[!] Fehler beim Verbinden mit \"$SSID\"."
            echo "    Prüfe SSID und Passwort."
            exit 2
        fi
    fi
else
    echo "[*] Erstelle neue Verbindung für \"$SSID\"..."
    if nmcli device wifi connect "$SSID" password "$PASS" ifname "$IFACE"; then
        echo "[+] Erfolgreich mit \"$SSID\" verbunden."
    else
        echo "[!] Fehler beim Verbinden mit \"$SSID\"."
        echo "    Prüfe:"
        echo "    - SSID und Passwort korrekt?"
        echo "    - SSID in Reichweite? (nmcli device wifi list)"
        echo "    - NetworkManager aktiv? (systemctl status NetworkManager)"
        exit 2
    fi
fi

# Warte auf IP-Zuweisung
echo "[*] Warte auf IP-Adresse..."
sleep 3

# Zeige Verbindungsinformationen
WLAN_IP=$(nmcli -t -f IP4.ADDRESS dev show "$IFACE" 2>/dev/null | grep 'IP4.ADDRESS' | cut -d: -f2 | cut -d/ -f1 | head -n1)

if [ -n "$WLAN_IP" ]; then
    echo "[+] Erfolgreich verbunden."
    echo "    WLAN-IP: $WLAN_IP"
    
    # Zeige Default-Route
    DEFAULT_ROUTE=$(ip route show default | grep "dev $IFACE")
    if [ -n "$DEFAULT_ROUTE" ]; then
        echo "    Default-Route: $DEFAULT_ROUTE"
    else
        echo "    [!] Warnung: Keine Default-Route über $IFACE gefunden."
    fi
else
    echo "[!] Warnung: Keine IPv4-Adresse erhalten."
    echo "    Verbindung könnte trotzdem funktionieren (DHCP verzögert)."
fi

# Zeige finale Routing-Tabelle für Debugging
echo "[*] Aktuelle Default-Routen:"
ip route show default

exit 0
