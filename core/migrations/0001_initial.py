# Generated for the first inventory schema (Django 5.2).
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Branch",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=24, unique=True, verbose_name="Clave de sucursal")),
                ("name", models.CharField(max_length=120, verbose_name="Nombre")),
                ("address", models.CharField(blank=True, max_length=255, verbose_name="Dirección o referencia")),
                ("is_demo", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("name",), "verbose_name": "Sucursal", "verbose_name_plural": "Sucursales"},
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=90, unique=True)),
            ],
            options={"ordering": ("name",), "verbose_name_plural": "Categorías"},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("sku", models.CharField(max_length=64, unique=True, verbose_name="Código de producto")),
                ("name", models.CharField(max_length=180, verbose_name="Producto")),
                ("brand", models.CharField(blank=True, max_length=100)),
                ("unit", models.CharField(default="pieza", max_length=30, verbose_name="Unidad de medida")),
                ("description", models.TextField(blank=True)),
                ("cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ("min_stock", models.PositiveIntegerField(default=5)),
                ("is_demo", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="core.category")),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="StorageLocation",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=70, verbose_name="Ubicación")),
                ("description", models.CharField(blank=True, max_length=160)),
                ("is_active", models.BooleanField(default=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="locations", to="core.branch")),
            ],
            options={"ordering": ("branch__name", "code")},
        ),
        migrations.CreateModel(
            name="StockBalance",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("quantity", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="balances", to="core.storagelocation")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="balances", to="core.product")),
            ],
        ),
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[
                    ("ENTRADA", "Entrada"), ("SALIDA", "Salida"), ("AJUSTE", "Ajuste"),
                    ("IMPORTACION", "Importación Excel"), ("DEMO", "Carga de demostración"),
                    ("TRASLADO_ENTRADA", "Traslado recibido"), ("TRASLADO_SALIDA", "Traslado enviado"),
                ], max_length=20)),
                ("delta", models.IntegerField(help_text="Variación firmada de unidades")),
                ("before", models.PositiveIntegerField()),
                ("after", models.PositiveIntegerField()),
                ("note", models.CharField(blank=True, max_length=255)),
                ("reference", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to=settings.AUTH_USER_MODEL)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movements", to="core.storagelocation")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movements", to="core.product")),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
        migrations.AddConstraint(
            model_name="storagelocation",
            constraint=models.UniqueConstraint(fields=("branch", "code"), name="uniq_location_in_branch"),
        ),
        migrations.AddConstraint(
            model_name="stockbalance",
            constraint=models.UniqueConstraint(fields=("product", "location"), name="uniq_product_location"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["-created_at"], name="movement_when_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["product", "-created_at"], name="movement_product_idx"),
        ),
    ]
