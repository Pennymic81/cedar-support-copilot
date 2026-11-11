#!/usr/bin/env bash
# Render build: install, collect static files, migrate, and load the Cedar Pay demo.
# Every step below is safe to repeat on each deploy.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input

if [ -n "$DEMO_ADMIN_PASSWORD" ]; then
  python manage.py seed_demo --username admin --password "$DEMO_ADMIN_PASSWORD"
else
  python manage.py seed_demo
fi
python manage.py load_evals --if-changed
python manage.py run_evals --label "deploy-${RENDER_GIT_COMMIT:0:7}" --quiet --if-stale
python manage.py simulate_traffic --if-empty
