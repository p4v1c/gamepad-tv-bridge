#!/usr/bin/env bash
# Lance Firefox en mode kiosque sur notre fork stremio-web (clavier virtuel TV),
# servi en statique sur http://127.0.0.1:8096 par stremio-web.service.
# Modèle : install/launch-youtube-tv.sh.
set -uo pipefail

URL="${STREMIO_TV_URL:-http://127.0.0.1:8096}"

# --- Trouver un serveur X joignable ------------------------------------------
# Sur le kiosk openbox l'affichage est :0 ; sous KDE/Wayland les applis X
# passent par Xwayland (souvent :1). On sonde avec xdotool plutôt que de coder
# l'affichage en dur.
pick_display() {
    if [ -n "${DISPLAY:-}" ] && xdotool getdisplaygeometry >/dev/null 2>&1; then
        return
    fi
    local d xa
    for d in :0 :1 :2; do
        for xa in ${XAUTHORITY:-} /run/user/"$(id -u)"/xauth_* "$HOME/.Xauthority"; do
            [ -e "$xa" ] || continue
            if DISPLAY="$d" XAUTHORITY="$xa" xdotool getdisplaygeometry >/dev/null 2>&1; then
                export DISPLAY="$d" XAUTHORITY="$xa"
                return
            fi
        done
    done
}
pick_display
echo "stremio-tv: DISPLAY=${DISPLAY:-unset} XAUTHORITY=${XAUTHORITY:-unset}"

# --- Attendre que l'UI statique réponde (le service peut démarrer en parallèle) ---
for _ in $(seq 1 30); do
    curl -sf -o /dev/null "$URL" && break
    sleep 1
done

# --- Profil Firefox dédié (comme youtube-tv) ---------------------------------
PROFILE_DIR="$HOME/.mozilla/firefox/stremio-tv"
if [ ! -d "$PROFILE_DIR" ]; then
    mkdir -p "$PROFILE_DIR"
    cat > "$PROFILE_DIR/user.js" <<EOF
user_pref("browser.startup.homepage", "$URL");
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("media.autoplay.default", 0);
EOF
fi

# Forcer le backend X11 : le bridge détecte la fenêtre active via X (xdotool).
# Sous une session Wayland (ex. KDE), Firefox démarrerait en Wayland natif —
# invisible à cette détection, donc le profil `stremio` ne matcherait pas.
# Sur le kiosk openbox X11 (déploiement cible) c'est un no-op.
export MOZ_ENABLE_WAYLAND=0
export GDK_BACKEND=x11

exec firefox --profile "$PROFILE_DIR" \
             --kiosk \
             "$URL"
