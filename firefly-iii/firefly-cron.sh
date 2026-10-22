#!/bin/sh
# Scheduled jobs for the firefly-cron container (busybox crond).
#
#   start   save the job env, install the crontab, exec crond (container command)
#   cron    Firefly III's daily maintenance (recurring transactions, bills, ...)
#   import  run every importer config in $IMPORT_DIR (SimpleFIN bank sync)
#
# crond starts jobs with an empty environment, so `start` saves the variables the
# jobs need to /run/firefly.env. Each job logs one line to the container log; a
# successful import pings $KUMA_PUSH_URL (if set) so a stopped import gets noticed.
set -u

log() { echo "$(date '+%F %T') $*" >> /proc/1/fd/1; }

case "${1:-}" in
  start)
    export -p | grep -E '^export (STATIC_CRON_TOKEN|AUTO_IMPORT_SECRET|IMPORT_DIR|KUMA_PUSH_URL)=' > /run/firefly.env
    printf '%s\n' \
      '0 5 * * * /bin/sh /firefly-cron.sh cron' \
      '0 6 * * * /bin/sh /firefly-cron.sh import' | crontab -
    exec crond -f -l 8
    ;;
  cron)
    . /run/firefly.env
    if wget -q -O /dev/null "http://firefly-iii:8080/api/v1/cron/$STATIC_CRON_TOKEN"; then
      log "cron: ok"
    else
      log "cron: FAILED"
      exit 1
    fi
    ;;
  import)
    . /run/firefly.env
    out=$(wget -q -O - --post-data= \
      "http://firefly-importer:8080/autoimport?directory=$IMPORT_DIR&secret=$AUTO_IMPORT_SECRET" 2>&1)
    case "$out" in
      *"Seems to have worked"*)
        log "import: ok"
        [ -n "${KUMA_PUSH_URL:-}" ] && wget -q -O /dev/null "$KUMA_PUSH_URL?status=up&msg=OK"
        ;;
      *)
        log "import: FAILED $(echo "$out" | head -c 300)"
        exit 1
        ;;
    esac
    ;;
  *)
    echo "usage: $0 start|cron|import" >&2
    exit 2
    ;;
esac
