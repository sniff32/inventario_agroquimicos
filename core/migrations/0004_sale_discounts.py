from decimal import Decimal
from django.db import migrations, models


def backfill_orders(apps, schema_editor):
    Sale = apps.get_model("core", "Sale")
    SaleItem = apps.get_model("core", "SaleItem")
    for item in SaleItem.objects.all().iterator():
        SaleItem.objects.filter(pk=item.pk).update(base_unit_price=item.unit_price)
    for sale in Sale.objects.all().iterator():
        Sale.objects.filter(pk=sale.pk).update(gross_subtotal=sale.subtotal)


class Migration(migrations.Migration):
    dependencies = [("core", "0003_sales")]

    operations = [
        migrations.AddField(
            model_name="sale", name="gross_subtotal",
            field=models.DecimalField(decimal_places=2, max_digits=14, default=0)
        ),
        migrations.AddField(
            model_name="sale", name="discount_total",
            field=models.DecimalField(decimal_places=2, max_digits=14, default=0)
        ),
        migrations.AddField(
            model_name="saleitem", name="base_unit_price",
            field=models.DecimalField(decimal_places=2, max_digits=12, default=0)
        ),
        migrations.AddField(
            model_name="saleitem", name="discount_percent",
            field=models.PositiveSmallIntegerField(default=0)
        ),
        migrations.AddField(
            model_name="saleitem", name="discount_total",
            field=models.DecimalField(decimal_places=2, max_digits=14, default=0)
        ),
        migrations.RunPython(backfill_orders, migrations.RunPython.noop),
    ]
