#!/bin/bash

# Install the package from Git repository
git pull
/home/pi/.local/bin/uv sync

# Run the dmScreen server
/home/pi/.local/bin/uv run dmScreen-server
