from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BranchStockMinimum",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("minimum", models.PositiveIntegerField(verbose_name="Mínimo en esta sucursal")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="stock_minimums", to="core.branch",
                )),
                ("product", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="branch_minimums", to="core.product",
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name="branchstockminimum",
            constraint=models.UniqueConstraint(
                fields=("product", "branch"), name="uniq_product_minimum_per_branch"
            ),
        ),
    ]
