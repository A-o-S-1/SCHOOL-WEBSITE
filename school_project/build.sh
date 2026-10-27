#!/usr/bin/env bash
set -o errexit
python -m pip install --upgrade pip
pip install -r requirements/prod.txt
python manage.py collectstatic --noinput
