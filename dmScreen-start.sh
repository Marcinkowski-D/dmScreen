#!/bin/bash
set -o pipefail

# Detect if we're on Linux
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[*] Linux erkannt, prüfe NetworkManager-Verfügbarkeit..."
    
    # Check if nmcli is available
    if ! command -v nmcli >/dev/null 2>&1; then
        echo "[!] nmcli nicht gefunden, installiere NetworkManager..."
        
        # Check if we have root privileges
        if [ "$EUID" -ne 0 ]; then
            echo "[!] Root-Rechte erforderlich für Installation. Versuche sudo..."
            sudo apt-get update
            sudo apt-get install -y network-manager
        else
            apt-get update
            apt-get install -y network-manager
        fi
        
        # Verify installation
        if ! command -v nmcli >/dev/null 2>&1; then
            echo "[!] FEHLER: NetworkManager-Installation fehlgeschlagen."
            echo "[!] Bitte manuell installieren: sudo apt-get install network-manager"
            exit 1
        fi
        
        echo "[+] NetworkManager erfolgreich installiert."
    else
        echo "[+] nmcli gefunden."
    fi
    
    # Ensure NetworkManager service is running
    if ! systemctl is-active --quiet NetworkManager; then
        echo "[*] Starte NetworkManager-Service..."
        if [ "$EUID" -ne 0 ]; then
            sudo systemctl enable NetworkManager
            sudo systemctl start NetworkManager
        else
            systemctl enable NetworkManager
            systemctl start NetworkManager
        fi
        sleep 2
    fi
    
    # Configure NetworkManager to manage wlan0 if needed
    # Remove dhcpcd interference if present
    if [ -f /etc/dhcpcd.conf ]; then
        if ! grep -q '^denyinterfaces wlan0' /etc/dhcpcd.conf 2>/dev/null; then
            echo "[*] Konfiguriere dhcpcd um wlan0-Konflikte zu vermeiden..."
            if [ "$EUID" -ne 0 ]; then
                echo "denyinterfaces wlan0" | sudo tee -a /etc/dhcpcd.conf >/dev/null
                sudo systemctl restart dhcpcd 2>/dev/null || true
            else
                echo "denyinterfaces wlan0" >> /etc/dhcpcd.conf
                systemctl restart dhcpcd 2>/dev/null || true
            fi
        fi
    fi
    
    echo "[+] NetworkManager ist bereit."
fi

# Start DHCP auf eth0 nur, wenn Link anliegt, und blockiere den Start nicht
if [ -r /sys/class/net/eth0/carrier ] && [ "$(cat /sys/class/net/eth0/carrier)" -eq 1 ]; then
    echo "[*] Ethernet-Verbindung erkannt, aktualisiere Repository..."
    
    # Use nmcli for Ethernet on Linux if available, otherwise fall back to dhclient
    if command -v nmcli >/dev/null 2>&1; then
        # NetworkManager should handle eth0 automatically
        # Just ensure the connection is up
        nmcli device connect eth0 2>/dev/null || true
        sleep 2
    else
        timeout 5s dhclient -1 eth0 || dhclient -nw eth0
    fi
    
    git checkout .
    git pull
    /home/pi/.local/bin/uv sync
fi

# Run the dmScreen server
# Get current WiFi SSID using nmcli if available, otherwise fall back to iwconfig
if command -v nmcli >/dev/null 2>&1; then
    WIFI_SSID=$(nmcli -t -f ACTIVE,SSID dev wifi | grep '^yes' | cut -d':' -f2)
else
    WIFI_SSID=$(iwconfig 2>/dev/null | grep "ESSID:" | awk -F'"' '{print $2}')
fi

if [ -n "$WIFI_SSID" ]; then
    echo "[*] Starte dmScreen-Server mit SSID: $WIFI_SSID"
    /home/pi/.local/bin/uv run dmScreen-server --ssid "$WIFI_SSID"
else
    echo "[*] Starte dmScreen-Server ohne SSID"
    /home/pi/.local/bin/uv run dmScreen-server
fi
