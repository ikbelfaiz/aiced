#!/bin/sh
set -eu
# Restrict substituted values to prevent configuration injection. Never echo key.
case "${AICED_GATEWAY_KEY:-}" in ''|*[!A-Za-z0-9_-]*) echo 'Invalid gateway key' >&2; exit 1;; esac
[ "${#AICED_GATEWAY_KEY}" -ge 32 ] || exit 1
INTEGRATION_UPSTREAM="${INTEGRATION_UPSTREAM:-$BACKEND_UPSTREAM}"
export INTEGRATION_UPSTREAM
for upstream in "$BACKEND_UPSTREAM" "$FRONTEND_UPSTREAM" "$INTEGRATION_UPSTREAM"; do
    case "$upstream" in ''|*[!A-Za-z0-9.:-]*) exit 1;; esac
done
case "$GATEWAY_PORT" in ''|*[!0-9]*) exit 1;; esac
case "$BACKEND_TIMEOUT" in ''|*[!0-9]*) exit 1;; esac
envsubst '${GATEWAY_PORT} ${BACKEND_UPSTREAM} ${INTEGRATION_UPSTREAM} ${FRONTEND_UPSTREAM} ${AICED_GATEWAY_KEY} ${BACKEND_TIMEOUT}' \
    < /opt/aiced/nginx.conf.template > /opt/aiced/nginx.conf
exec nginx -p /opt/aiced/ -c nginx.conf -g 'daemon off;'
