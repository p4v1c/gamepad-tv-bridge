#!/usr/bin/env bash
#
# setup-stremio.sh — installe les services utilisateur Stremio TV :
#   - stremio-server.service : serveur de streaming local (11470)   [activé]
#   - stremio-web.service    : sert le build du fork stremio-web (8096) [activé]
#   - stremio-tv.service     : Firefox kiosk sur l'UI forkée (clavier virtuel)
#                              [installé mais PAS activé : le kiosk se lance
#                              depuis la tuile Stremio de GameCore (apps.json),
#                              ou manuellement via systemctl --user start]
#
# Prérequis : le fork stremio-web construit dans ~/stremio-web (voir README).
#
# Usage :
#   ./setup-stremio.sh              # installe + active
#   ./setup-stremio.sh --uninstall  # retire tout
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNITS=(stremio-server.service stremio-web.service stremio-tv.service)

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now "${UNITS[@]}" 2>/dev/null || true
    for u in "${UNITS[@]}"; do rm -f "$UNIT_DIR/$u"; done
    systemctl --user daemon-reload 2>/dev/null || true
    echo "✅ Services Stremio TV désinstallés."
    exit 0
fi

BUILD_DIR="$HOME/stremio-web/build"
if [ ! -f "$BUILD_DIR/index.html" ]; then
    echo "⚠️  $BUILD_DIR/index.html introuvable — construis d'abord le fork :" >&2
    echo "    cd ~/stremio-web && pnpm install && pnpm build" >&2
fi

mkdir -p "$UNIT_DIR"
chmod +x "$HERE/launch-stremio.sh"
for u in "${UNITS[@]}"; do
    cp "$HERE/$u" "$UNIT_DIR/$u"
    echo "• installé : $u"
done

# daemon-reload + enable via le bus utilisateur si dispo. Seuls les backends
# démarrent avec la session ; le kiosk (stremio-tv) est lancé à la demande par
# la tuile Stremio de GameCore.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable stremio-server.service stremio-web.service 2>/dev/null || true
    systemctl --user disable stremio-tv.service 2>/dev/null || true
    echo "✅ Backends activés (démarrage à l'ouverture de session)."
    echo "   Kiosk : tuile Stremio de GameCore, ou :  systemctl --user start stremio-tv.service"
else
    echo "ℹ️  Pas de bus utilisateur ici — les backends démarreront au prochain login."
fi
