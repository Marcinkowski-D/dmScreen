#!/bin/bash
/bin/bash stop-ap.sh
/bin/bash start-ap.sh
dhclient eth0
# Install the package from Git repository
git checkout .
git pull

/home/pi/.local/bin/uv sync

# Run the dmScreen server
/home/pi/.local/bin/uv run dmScreen-server
