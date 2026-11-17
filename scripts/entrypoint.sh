#!/bin/sh
set -eu
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8080}" --workers 2 --threads 4 --timeout 60 --no-control-socket --access-logfile - --error-logfile -
