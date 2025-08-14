#!/bin/bash
/bin/bash stop-ap.sh
/bin/bash start-ap.sh
if ip link show eth0 >/dev/null 2>&1; then
    dhclient eth0
fi
# Install the package from Git repository
git checkout .
git pull

/home/pi/.local/bin/uv sync

# Run the dmScreen server
/home/pi/.local/bin/uv run dmScreen-server
