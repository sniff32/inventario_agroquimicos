"""Precios mayoristas FICTICIOS solo para artículos DEMO existentes."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import migrations


def seed_demo_wholesale(apps, schema_editor):
    Product = apps.get_model("core", "Product")
    for product in Product.objects.filter(is_demo=True, wholesale_price__isnull=True):
        product.wholesale_price = (Decimal(product.price) * Decimal("0.92")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        product.wholesale_min_qty = 10
        product.save(update_fields=["wholesale_price", "wholesale_min_qty"])


class Migration(migrations.Migration):
    dependencies = [("core", "0004_sale_discounts")]
    operations = [migrations.RunPython(seed_demo_wholesale, migrations.RunPython.noop)]
