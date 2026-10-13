#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python -m compileall -q config core
python manage.py check
python manage.py shell -c "from django.template.loader import get_template; [get_template(name) for name in ['dashboard.html', 'inventory/content.html', 'registration/login.html']]"
python manage.py collectstatic --noinput
python manage.py migrate --noinput

# Inicialización extraordinaria y controlada del primer administrador.
# No se ejecuta si BOOTSTRAP_ADMIN no es true.
# El comando no altera administradores ya existentes.
if [[ "${BOOTSTRAP_ADMIN:-false}" == "true" ]]; then
  python manage.py bootstrap_admin
fi
