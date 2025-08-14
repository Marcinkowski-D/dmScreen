#!/bin/bash
/bin/bash stop-ap.sh
/bin/bash start-ap.sh
# Start DHCP auf eth0 nur, wenn Link anliegt, und blockiere den Start nicht
if [ -r /sys/class/net/eth0/carrier ] && [ "$(cat /sys/class/net/eth0/carrier)" -eq 1 ]; then
    timeout 5s dhclient -1 eth0 || dhclient -nw eth0
    git checkout .
    git pull
    /home/pi/.local/bin/uv sync
fi

# Run the dmScreen server
/home/pi/.local/bin/uv run dmScreen-server
