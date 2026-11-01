#!/usr/bin/env bash
# Render build step: install, collect static files, migrate, create the admin account once.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --no-input || echo "Superuser already exists, skipping."
fi
