#!/bin/sh
set -eu
# Restrict substituted values to prevent configuration injection. Never echo key.
case "${AICED_GATEWAY_KEY:-}" in ''|*[!A-Za-z0-9_-]*) echo 'Invalid gateway key' >&2; exit 1;; esac
[ "${#AICED_GATEWAY_KEY}" -ge 32 ] || exit 1
if [ "${AICED_REQUIRE_SERVICES:-0}" = 1 ]; then
    : "${INTEGRATION_UPSTREAM:?Independent Integration upstream required}"
    : "${IAM_UPSTREAM:?Independent IAM upstream required}"
    : "${COMMERCIAL_UPSTREAM:?Independent Commercial upstream required}"
    [ "$INTEGRATION_UPSTREAM" != "$BACKEND_UPSTREAM" ] || exit 1
    [ "$IAM_UPSTREAM" != "$BACKEND_UPSTREAM" ] || exit 1
    [ "$COMMERCIAL_UPSTREAM" != "$BACKEND_UPSTREAM" ] || exit 1
fi
INTEGRATION_UPSTREAM="${INTEGRATION_UPSTREAM:-$BACKEND_UPSTREAM}"
IAM_UPSTREAM="${IAM_UPSTREAM:-$BACKEND_UPSTREAM}"
COMMERCIAL_UPSTREAM="${COMMERCIAL_UPSTREAM:-$BACKEND_UPSTREAM}"
export INTEGRATION_UPSTREAM IAM_UPSTREAM COMMERCIAL_UPSTREAM
for upstream in "$BACKEND_UPSTREAM" "$FRONTEND_UPSTREAM" "$INTEGRATION_UPSTREAM" "$IAM_UPSTREAM" "$COMMERCIAL_UPSTREAM"; do
    case "$upstream" in ''|*[!A-Za-z0-9.:-]*) exit 1;; esac
done
case "$GATEWAY_PORT" in ''|*[!0-9]*) exit 1;; esac
case "$BACKEND_TIMEOUT" in ''|*[!0-9]*) exit 1;; esac
envsubst '${GATEWAY_PORT} ${BACKEND_UPSTREAM} ${INTEGRATION_UPSTREAM} ${IAM_UPSTREAM} ${COMMERCIAL_UPSTREAM} ${FRONTEND_UPSTREAM} ${AICED_GATEWAY_KEY} ${BACKEND_TIMEOUT}' \
    < /opt/aiced/nginx.conf.template > /opt/aiced/nginx.conf
exec nginx -p /opt/aiced/ -c nginx.conf -g 'daemon off;'
