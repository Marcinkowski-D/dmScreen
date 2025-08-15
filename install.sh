#!/bin/bash
# install.sh – Installiere alle benötigten Pakete und bereite Dienste für dmScreen WiFi/AP vor
# Nutze: sudo ./install.sh

set -euo pipefail

[ "$EUID" -eq 0 ] || { echo "Bitte mit sudo ausführen."; exit 1; }

export DEBIAN_FRONTEND=noninteractive

echo "[*] Paketquellen aktualisieren ..."
apt-get update -y

echo "[*] Installiere erforderliche Pakete ..."
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
  git \
  chromium-browser
  
git config --global --add safe.directory $(pwd)

# Dienste vorbereiten
echo "[*] Dienste vorbereiten ..."
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

# Region auf DE setzen (kann für 2,4GHz APs wichtig sein)
iw reg set DE 2>/dev/null || true

# Install uv if not already present
if ! command -v uv &> /dev/null; then
    echo "[*] Installing uv package installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo "[*] Creating systemd service..."
mkdir -p /etc/systemd/system
cat > /etc/systemd/system/dmscreen.service << 'EOF'
[Unit]
Description=DM Screen Webserver
After=network.target

[Service]
User=root
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/bash dmScreen-start.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl enable dmscreen.service

echo "[*] Creating autostart entry for kiosk mode..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/kiosk.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=KioskBrowser
Exec=chromium-browser --disable-features=LowMemoryMonitor --noerrdialogs --kiosk http://127.0.0.1/view
X-GNOME-Autostart-enabled=true
EOF

cat <<MSG

[✓] Installation abgeschlossen.

MSG
