#!/usr/bin/env bash
#
# stremio-server.sh — lance le serveur de streaming Stremio (EngineFS, 11470).
#
# On réutilise le `server.js` officiel embarqué dans le Flatpak Stremio, mais on
# l'exécute de préférence avec le **node de l'hôte**, pas avec celui du Flatpak.
#
# Pourquoi : le ffmpeg du runtime Flatpak est compilé avec
#     --disable-decoder='h264,hevc,vc1,vvc'
# Il ne sait donc pas décoder le HEVC, et le H.264 ne lui reste accessible que
# via libopenh264 (logiciel, accélération VAAPI impossible). Or l'UI web sert
# presque toujours du MKV via le transcodeur HLS du serveur (cf docs) :
#   • source x265 → ffmpeg meurt sur « no decoder found for: hevc », le serveur
#     répond {"error":{"code":10,"message":"Failed to read hls playlist:
#     Premature close"}} et le lecteur attend indéfiniment ;
#   • source x264 → décodage logiciel seul, démarrage très lent.
# Le ffmpeg système, lui, a les décodeurs complets (et VAAPI si le GPU suit).
#
# Si l'hôte n'a pas de node ou pas de ffmpeg capable, on retombe proprement sur
# le node du Flatpak : le serveur démarre quand même, seul le transcodage des
# formats exotiques reste dégradé.
set -euo pipefail

APP_ID=com.stremio.Stremio

# ── 1. Localiser server.js (install Flatpak système OU utilisateur) ──────────
SERVER_JS=""
if FLATPAK_DIR="$(flatpak info --show-location "$APP_ID" 2>/dev/null)"; then
    [ -f "$FLATPAK_DIR/files/opt/stremio/server.js" ] \
        && SERVER_JS="$FLATPAK_DIR/files/opt/stremio/server.js"
fi
if [ -z "$SERVER_JS" ]; then
    for candidate in \
        "/var/lib/flatpak/app/$APP_ID/current/active/files/opt/stremio/server.js" \
        "$HOME/.local/share/flatpak/app/$APP_ID/current/active/files/opt/stremio/server.js"
    do
        [ -f "$candidate" ] && { SERVER_JS="$candidate"; break; }
    done
fi
if [ -z "$SERVER_JS" ]; then
    echo "stremio-server: server.js introuvable — le Flatpak $APP_ID est-il installé ?" >&2
    exit 1
fi

# ── 2. Le ffmpeg de l'hôte sait-il décoder le HEVC ? ─────────────────────────
# NB : awk consomme toute l'entrée et signale via son code de sortie. Un
# `grep -q` fermerait le tube au premier match → SIGPIPE (141) en amont → avec
# `set -o pipefail` le test échouerait toujours, et on retomberait à tort sur le
# node du Flatpak.
host_ffmpeg_is_capable() {
    command -v ffmpeg >/dev/null 2>&1 || return 1
    command -v ffprobe >/dev/null 2>&1 || return 1
    ffmpeg -hide_banner -decoders 2>/dev/null | awk '$2 == "hevc" { found = 1 } END { exit !found }'
}

# ── 3. Choisir l'interpréteur ────────────────────────────────────────────────
if command -v node >/dev/null 2>&1 && host_ffmpeg_is_capable; then
    exec node "$SERVER_JS"
fi

if command -v node >/dev/null 2>&1; then
    echo "stremio-server: ffmpeg hôte absent ou sans décodeur HEVC — installe le paquet" >&2
    echo "                'ffmpeg' pour que le transcodage des sources x265 fonctionne." >&2
else
    echo "stremio-server: node introuvable sur l'hôte — installe le paquet 'nodejs'." >&2
fi
echo "stremio-server: repli sur le node du Flatpak (transcodage HEVC indisponible)." >&2
exec flatpak run --command=node "$APP_ID" /app/opt/stremio/server.js
