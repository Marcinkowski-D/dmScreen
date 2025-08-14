#!/bin/bash
# install.sh – Installiere alle benötigten Pakete und bereite Dienste für dmScreen WiFi/AP vor
# Nutze: sudo ./install.sh

set -euo pipefail

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

export DEBIAN_FRONTEND=noninteractive

echo "[*] Paketquellen aktualisieren …"
apt-get update -y

echo "[*] Installiere erforderliche Pakete …"
# hostapd/dnsmasq für AP, iw/wireless-tools für Scans, iproute2 für ip, dhclient für DHCP, rfkill zum Entsperren,
# net-tools optional (ifconfig), wpasupplicant für Client-Betrieb, curl/git optional (Updater, Tools)
apt-get install -y \
  hostapd \
  dnsmasq \
  iw \
  wireless-tools \
  iproute2 \
  isc-dhcp-client \
  rfkill \
  net-tools \
  wpasupplicant \
  curl \
  git

# Dienste vorbereiten
echo "[*] Dienste vorbereiten …"
systemctl unmask hostapd || true
systemctl enable hostapd || true
systemctl enable dnsmasq || true

# dnsmasq.d sicherstellen (start-ap.sh verwendet ein Snippet)
mkdir -p /etc/dnsmasq.d

# dhcpcd soll wlan0 nicht automatisch verwalten (Konflikte mit dhclient vermeiden)
if [ -f /etc/dhcpcd.conf ]; then
  if ! grep -q '^denyinterfaces .*wlan0' /etc/dhcpcd.conf; then
    echo "denyinterfaces wlan0" >> /etc/dhcpcd.conf
    systemctl daemon-reload || true
    systemctl restart dhcpcd || true
  fi
fi

# Skripte ausführbar machen
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$SCRIPT_DIR/start-ap.sh" || true
chmod +x "$SCRIPT_DIR/stop-ap.sh" || true
chmod +x "$SCRIPT_DIR/connect-wifi.sh" || true
chmod +x "$SCRIPT_DIR/forget-wifi.sh" || true
chmod +x "$SCRIPT_DIR/wifi-check.sh" || true
[ -f "$SCRIPT_DIR/dmScreen-start.sh" ] && chmod +x "$SCRIPT_DIR/dmScreen-start.sh" || true

# Region auf DE setzen (kann für 2,4GHz APs wichtig sein)
iw reg set DE 2>/dev/null || true

cat <<MSG

[✓] Installation abgeschlossen.

Nächste Schritte / Hinweise:
- Starte den Dienst/Server deiner Anwendung. Beim Boot/Start wird der AP zuerst aktiviert,
  danach wird – falls bekannte WLANs vorhanden und sichtbar sind – die Verbindung versucht.
- AP-Start manuell: sudo "$SCRIPT_DIR/start-ap.sh"
- AP-Stop:          sudo "$SCRIPT_DIR/stop-ap.sh"
- WLAN verbinden:   sudo "$SCRIPT_DIR/connect-wifi.sh" "SSID" "PASSWORT"

MSG
