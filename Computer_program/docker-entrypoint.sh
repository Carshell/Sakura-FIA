#!/bin/sh
set -e

DASHBOARD_HOST="${DASHBOARD_HOST:-http://dashboard:5000}"
VIDEO_SCRIPT="${VIDEO_SCRIPT:-video_get.py}"

echo "Очікування дашборду: ${DASHBOARD_HOST}"
until wget -q -O /dev/null "${DASHBOARD_HOST}/api/targets" 2>/dev/null; do
    sleep 1
done

echo "Дашборд готовий. Запуск: ${VIDEO_SCRIPT}"
exec python "${VIDEO_SCRIPT}"
