#!/bin/bash
if ! iwconfig 2>/dev/null | grep -q "ESSID:\""; then
    /bin/bash stop-ap.sh
    /bin/bash start-ap.sh
fi
# Start DHCP auf eth0 nur, wenn Link anliegt, und blockiere den Start nicht
if [ -r /sys/class/net/eth0/carrier ] && [ "$(cat /sys/class/net/eth0/carrier)" -eq 1 ]; then
    timeout 5s dhclient -1 eth0 || dhclient -nw eth0
    git checkout .
    git pull
    /home/pi/.local/bin/uv sync
fi

# Run the dmScreen server
WIFI_SSID=$(iwconfig 2>/dev/null | grep "ESSID:" | awk -F'"' '{print $2}')
if [ -n "$WIFI_SSID" ]; then
    /home/pi/.local/bin/uv run dmScreen-server --ssid "$WIFI_SSID"
else
    /home/pi/.local/bin/uv run dmScreen-server
fi
