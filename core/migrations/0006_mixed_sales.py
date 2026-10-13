from django.db import migrations, models


def preserve_previous_sales(apps, schema_editor):
    """Las órdenes existentes eran exclusivamente mayoreo o menudeo."""
    SaleItem = apps.get_model("core", "SaleItem")
    SaleItem.objects.filter(sale__sale_type="MAYOREO").update(sale_type="MAYOREO")


class Migration(migrations.Migration):
    dependencies = [("core", "0005_demo_wholesale")]

    operations = [
        migrations.AlterField(
            model_name="sale", name="sale_type",
            field=models.CharField(
                "Tipo de venta", max_length=12,
                choices=[("MENUDEO", "Menudeo"), ("MAYOREO", "Mayoreo"), ("MIXTA", "Mixta")],
            ),
        ),
        migrations.AddField(
            model_name="saleitem", name="sale_type",
            field=models.CharField(
                "Modalidad del artículo", max_length=12, default="MENUDEO",
                choices=[("MENUDEO", "Menudeo"), ("MAYOREO", "Mayoreo")],
            ),
        ),
        migrations.RunPython(preserve_previous_sales, migrations.RunPython.noop),
    ]
