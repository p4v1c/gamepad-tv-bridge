#!/usr/bin/env bash
# Lance Firefox en mode kiosque sur YouTube TV avec un user-agent Smart TV

UA="Mozilla/5.0 (SMART-TV; Linux; Tizen 6.0) AppleWebKit/538.1 (KHTML, like Gecko) Version/6.0 TV Safari/538.1"

# Crée un profil Firefox dédié si pas encore fait
PROFILE_DIR="$HOME/.mozilla/firefox/youtube-tv"
if [ ! -d "$PROFILE_DIR" ]; then
    mkdir -p "$PROFILE_DIR"
    cat > "$PROFILE_DIR/user.js" <<EOF
user_pref("general.useragent.override", "$UA");
user_pref("browser.startup.homepage", "https://www.youtube.com/tv");
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
EOF
fi

firefox --profile "$PROFILE_DIR" \
        --kiosk \
        "https://www.youtube.com/tv"
