#!/bin/bash

# Install the package from Git repository
git pull
uv sync

# Run the dmScreen server
uv run dmScreen-server
