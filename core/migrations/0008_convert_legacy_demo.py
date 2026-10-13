"""Cambio de giro de la demostración en una base ya utilizada.

Sólo si existen artículos electrónicos marcados DEMO y una cuenta administradora.
No borra nada: desactiva la demostración anterior y crea la nueva.
"""
from django.contrib.auth import get_user_model
from django.db import migrations


def migrate_existing_demo(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    if not Product.objects.filter(is_demo=True, sku__startswith="DEMO-", is_active=True).exists():
        return
    actor = get_user_model().objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
    if actor is None:
        return
    # En esta versión del esquema los modelos runtime equivalen a los históricos.
    # La función conserva movimientos y ventas, y es idempotente.
    from core.demo import load_demo
    load_demo(actor=actor)


class Migration(migrations.Migration):
    dependencies = [("core", "0007_finance")]
    operations = [
        migrations.RunPython(migrate_existing_demo, migrations.RunPython.noop),
    ]
