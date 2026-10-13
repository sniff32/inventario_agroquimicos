from django.db import migrations, models
import django.db.models.deletion


def create_greenhouses(apps, schema_editor):
    Greenhouse = apps.get_model("core", "Greenhouse")
    for index in range(1, 6):
        Greenhouse.objects.get_or_create(code=f"INV-{index:02d}", defaults={"name": f"Invernadero {index:02d}", "is_demo": True})


class Migration(migrations.Migration):
    dependencies = [("core", "0009_agro_identity")]

    operations = [
        migrations.CreateModel(name="Greenhouse", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("code", models.CharField(max_length=24, unique=True)),
            ("name", models.CharField(max_length=120)),
            ("crop", models.CharField(blank=True, max_length=120)),
            ("description", models.CharField(blank=True, max_length=250)),
            ("is_active", models.BooleanField(default=True)),
            ("is_demo", models.BooleanField(default=False)),
        ], options={"ordering": ("code",)}),
        migrations.CreateModel(name="GreenhouseReading", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("recorded_at", models.DateTimeField(db_index=True)),
            ("temperature", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
            ("humidity", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
            ("soil_moisture", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
            ("light_lux", models.PositiveIntegerField(blank=True, null=True)),
            ("tank_level", models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True)),
            ("irrigation_on", models.BooleanField(default=False)),
            ("ventilation_on", models.BooleanField(default=False)),
            ("is_demo", models.BooleanField(default=False)),
            ("greenhouse", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="readings", to="core.greenhouse")),
        ], options={"ordering": ("-recorded_at",)}),
        migrations.AddIndex(model_name="greenhousereading", index=models.Index(fields=["greenhouse", "-recorded_at"], name="greenhouse_reading_recent_idx")),
        migrations.RunPython(create_greenhouses, migrations.RunPython.noop),
    ]
