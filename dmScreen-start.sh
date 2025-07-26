#!/bin/bash

# Install the package from Git repository
uv pip install git+https://github.com/youruser/dmScreen.git

# Run the dmScreen server
uv run dmScreen-server
