#!/usr/bin/env bash
set -euo pipefail

echo "==> Chargement du module uinput"
sudo modprobe uinput

echo "==> Persistance du module au démarrage"
echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf > /dev/null

echo "==> Règle udev pour /dev/uinput (groupe input, mode 660)"
sudo tee /etc/udev/rules.d/99-uinput.rules > /dev/null <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF

echo "==> Rechargement udev"
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "==> Ajout de $USER au groupe input"
sudo usermod -aG input "$USER"

echo ""
echo "Tout est prêt. Lance maintenant :"
echo "  newgrp input"
echo "  .venv/bin/python -m gamepad_bridge start"
