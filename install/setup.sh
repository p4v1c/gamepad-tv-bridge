#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$HOME/.venv"
SERVICE_DIR="$HOME/.config/systemd/user"

echo "==> Creating virtual environment at $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip --quiet
"$VENV/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet
"$VENV/bin/pip" install -e "$PROJECT_DIR" --quiet

echo "==> Installing systemd user service"
mkdir -p "$SERVICE_DIR"
cp "$SCRIPT_DIR/gamepad-tv-bridge.service" "$SERVICE_DIR/"
systemctl --user daemon-reload
# The unit used to be WantedBy=graphical-session.target, and `enable` does not
# clean up the symlink a previous [Install] left behind. Left there it is not
# merely untidy: on a GameCore box that target is only reached by the KDE
# desktop, never by the kiosk session, which is exactly where the daemon has to
# run. Drop it explicitly before enabling.
rm -f "$SERVICE_DIR/graphical-session.target.wants/gamepad-tv-bridge.service"
systemctl --user enable gamepad-tv-bridge.service

echo "==> Checking input group membership"
if ! groups | grep -qw input; then
    echo "WARNING: You are not in the 'input' group."
    echo "         Run: sudo usermod -aG input \$USER"
    echo "         Then log out and back in."
fi

echo ""
echo "Done! Start with:"
echo "  systemctl --user start gamepad-tv-bridge"
echo "  journalctl --user -fu gamepad-tv-bridge"
