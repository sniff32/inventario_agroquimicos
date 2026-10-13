from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_mixed_sales"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="Supplier",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=180, unique=True, verbose_name="Proveedor")),
                ("contact", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=60)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=180, unique=True, verbose_name="Cliente o abarrotera")),
                ("contact", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=60)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.AddField(
            model_name="sale", name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="sales", to="core.customer"),
        ),
        migrations.AddField(
            model_name="sale", name="payment_term",
            field=models.CharField(max_length=16, choices=[
                ("SIN_CLASIFICAR", "Sin clasificar"), ("CONTADO", "Contado"), ("CREDITO", "Crédito"),
            ], default="SIN_CLASIFICAR"),
        ),
        migrations.AddField(
            model_name="sale", name="due_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("quantity", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("unit_cost", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
                ("total", models.DecimalField(decimal_places=2, max_digits=14)),
                ("term", models.CharField(max_length=10, choices=[("CONTADO","Contado"),("CREDITO","Crédito")])),
                ("due_date", models.DateField(blank=True, null=True)),
                ("reference", models.CharField(blank=True, max_length=80)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.storagelocation")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchases", to="core.product")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchases", to="core.supplier")),
            ],
            options={"ordering": ("-created_at","-pk")},
        ),
        migrations.CreateModel(
            name="PurchasePayment",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ("reference", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("purchase", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="core.purchase")),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("created_at","pk")},
        ),
        migrations.CreateModel(
            name="SalePayment",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ("reference", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sale", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="core.sale")),
                ("recorded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("created_at","pk")},
        ),
    ]
