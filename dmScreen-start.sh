#!/bin/bash

dhclient eth0
# Install the package from Git repository
git checkout .
git pull
chmod +x connect-wifi.sh
chmod +x forget-wifi.sh
chmod +x start-ap.sh
chmod +x stop-ap.sh
# sudo ./connect-wifi.sh "SSID" "Passwort"
# sudo ./forget-wifi.sh
# sudo ./start-ap.sh
# sudo ./stop-ap.sh

/home/pi/.local/bin/uv sync

# Run the dmScreen server
/home/pi/.local/bin/uv run dmScreen-server
