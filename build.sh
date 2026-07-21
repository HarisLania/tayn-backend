#!/usr/bin/env bash
# Render build command: ./build.sh
# Runs on every deploy: install deps, collect static assets, apply migrations.
set -o errexit

pip install -r requirements.txt

# Required: admin + Swagger UI assets are served by WhiteNoise from
# STATIC_ROOT, and ManifestStaticFilesStorage 500s on any page that
# references a file missing from staticfiles.json.
python manage.py collectstatic --no-input

python manage.py migrate --no-input
