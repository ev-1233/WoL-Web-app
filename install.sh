#!/bin/bash
#
# WOL Gateway One-Line Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/yourusername/wol-gateway/main/install.sh | bash
#

set -e

REPO="yourusername/wol-gateway"
INSTALL_DIR="$HOME/wol-gateway"

echo "======================================"
echo "   WOL Gateway Installer"
echo "======================================"
echo ""

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y git
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y git
    elif command -v yum &> /dev/null; then
        sudo yum install -y git
    else
        echo "Error: Cannot install git automatically."
        echo "Please install git manually and try again."
        exit 1
    fi
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Please install Python 3 and try again."
    exit 1
fi

# Clone or update repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Downloading WOL Gateway..."
    git clone "https://github.com/$REPO.git" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Make scripts executable
chmod +x setup_wol.py start.sh 2>/dev/null || true

echo ""
echo "======================================"
echo "   Installation Complete!"
echo "======================================"
echo ""
echo "Starting setup wizard..."
echo ""

# Run setup
python3 setup_wol.py

echo ""
echo "======================================"
echo "   Setup Complete!"
echo "======================================"
echo ""
echo "Location: $INSTALL_DIR"
echo ""
echo "Useful commands:"
echo "  Start:    cd $INSTALL_DIR && ./start.sh"
echo "  Reconfigure: cd $INSTALL_DIR && python3 setup_wol.py"
echo ""
