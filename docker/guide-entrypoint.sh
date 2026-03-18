#!/bin/sh
# Genera htpasswd a runtime da env var (password non baked nell'immagine)
htpasswd -bc /etc/nginx/.htpasswd "${GUIDE_USER:-opz}" "${GUIDE_PASSWORD:?GUIDE_PASSWORD env var required}"
exec nginx -g "daemon off;"
