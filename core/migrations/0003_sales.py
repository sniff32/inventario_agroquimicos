from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_branchstockminimum"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="product", name="wholesale_price",
            field=models.DecimalField(
                verbose_name="Precio mayoreo", decimal_places=2, max_digits=12,
                null=True, blank=True, validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="product", name="wholesale_min_qty",
            field=models.PositiveIntegerField(
                verbose_name="Unidades mínimas mayoreo", default=10,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.CreateModel(
            name="SaleSequence",
            fields=[
                ("name", models.CharField(primary_key=True, max_length=20, default="FERMO", serialize=False)),
                ("last_number", models.PositiveIntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name="Sale",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("number", models.CharField(verbose_name="Folio", max_length=24, unique=True)),
                ("sale_type", models.CharField(
                    verbose_name="Tipo de venta", max_length=12,
                    choices=[("MENUDEO", "Menudeo"), ("MAYOREO", "Mayoreo")],
                )),
                ("customer_name", models.CharField(verbose_name="Cliente", max_length=180)),
                ("customer_contact", models.CharField(verbose_name="Contacto", max_length=120, blank=True)),
                ("delivery_date", models.DateField(verbose_name="Fecha de salida / entrega")),
                ("note", models.CharField(verbose_name="Observaciones", max_length=255, blank=True)),
                ("subtotal", models.DecimalField(max_digits=14, decimal_places=2)),
                ("currency", models.CharField(max_length=3, default="MXN")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("branch", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="sales", to="core.branch"
                )),
                ("created_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="sales_created",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ("-created_at", "-id"),
                "indexes": [models.Index(fields=["-created_at"], name="sale_created_idx")],
            },
        ),
        migrations.CreateModel(
            name="SaleItem",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("sku_snapshot", models.CharField(max_length=64)),
                ("name_snapshot", models.CharField(max_length=180)),
                ("quantity", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("unit_price", models.DecimalField(max_digits=12, decimal_places=2)),
                ("line_total", models.DecimalField(max_digits=14, decimal_places=2)),
                ("location", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="sale_items", to="core.storagelocation"
                )),
                ("product", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="sale_items", to="core.product"
                )),
                ("sale", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name="items", to="core.sale"
                )),
            ],
            options={"ordering": ("id",)},
        ),
    ]
