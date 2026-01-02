#!/bin/bash
#
# Setup script to create virtual environment for Script Server
# Run this inside the script-server container:
#   docker exec -it script-server /app/scripts/setup_venvs.sh
#

set -e

VENV_DIR="/app/scripts/venv"

echo "=============================================="
echo "Script Server - Virtual Environment Setup"
echo "=============================================="
echo ""

if [ -d "$VENV_DIR" ]; then
    echo "Venv already exists at $VENV_DIR"
    echo "Reinstalling packages..."
else
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "Upgrading pip..."
"$VENV_DIR/bin/pip" install --upgrade pip -q

echo "Installing packages..."
"$VENV_DIR/bin/pip" install requests rich pandas numpy pydrive2 -q

echo ""
echo "Installed packages:"
"$VENV_DIR/bin/pip" list --format=freeze | grep -v "^pip=\|^setuptools="

echo ""
echo "=============================================="
echo "Virtual environment ready!"
echo "=============================================="
echo ""
echo "Use this Python interpreter in your scripts:"
echo "  $VENV_DIR/bin/python"
