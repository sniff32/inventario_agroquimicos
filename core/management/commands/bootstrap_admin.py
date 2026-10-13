"""Crear una sola vez el primer administrador, sin claves en el repositorio."""
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction


class Command(BaseCommand):
    help = "Crea el primer superusuario usando variables privadas del entorno."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")

        # Primero verificar si ya existe alguno para no cambiar credenciales
        # accidentalmente en ejecuciones o despliegues posteriores.
        User = get_user_model()
        with transaction.atomic():
            if User.objects.filter(is_superuser=True).exists():
                self.stdout.write("Ya existe un administrador; no se realizaron cambios.")
                return

            if not username or not email or not password:
                raise CommandError(
                    "Faltan DJANGO_SUPERUSER_USERNAME, "
                    "DJANGO_SUPERUSER_EMAIL o DJANGO_SUPERUSER_PASSWORD."
                )

            if User.objects.filter(username=username).exists():
                raise CommandError("El nombre de usuario indicado ya está en uso.")

            user = User(username=username, email=email)
            try:
                validate_email(email)
                validate_password(password, user=user)
            except ValidationError as exc:
                raise CommandError(
                    "El correo o la contraseña no cumple las validaciones: "
                    + "; ".join(exc.messages)
                ) from exc

            user.is_staff = True
            user.is_superuser = True
            user.set_password(password)
            user.save()

        self.stdout.write(
            self.style.SUCCESS("Primer administrador creado correctamente.")
        )
