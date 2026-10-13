from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0008_convert_legacy_demo")]

    operations = [
        migrations.AlterField(
            model_name="salesequence",
            name="name",
            field=models.CharField(default="AGROQUIMICOS", max_length=20, primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="customer",
            name="name",
            field=models.CharField(max_length=180, unique=True, verbose_name="Cliente o productor"),
        ),
    ]
