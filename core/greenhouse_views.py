"""Panel de lectura de invernaderos. Sin datos reales no se afirma conectividad."""
from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from .models import Greenhouse, GreenhouseReading


def greenhouse_context():
    now = timezone.now()
    latest = GreenhouseReading.objects.filter(greenhouse=OuterRef("pk")).order_by("-recorded_at")
    items = Greenhouse.objects.filter(is_active=True).annotate(
        last_reading_id=Subquery(latest.values("pk")[:1])
    )
    readings = GreenhouseReading.objects.filter(pk__in=[
        obj.last_reading_id for obj in items if obj.last_reading_id
    ])
    by_id = {reading.pk: reading for reading in readings}
    rows = []
    online = alerts = 0
    demo_count = 0
    for greenhouse in items:
        reading = by_id.get(greenhouse.last_reading_id)
        is_recent = bool(reading and not reading.is_demo and
                         now - timedelta(minutes=5) <= reading.recorded_at <= now)
        if is_recent:
            online += 1
        if reading and reading.is_demo:
            demo_count += 1
        # Los umbrales son referencias visuales, no controles automáticos.
        alert = bool(is_recent and (
            (reading.temperature is not None and (reading.temperature < 15 or reading.temperature > 35))
            or (reading.humidity is not None and (reading.humidity < 35 or reading.humidity > 90))
        ))
        alerts += int(alert)
        rows.append({"greenhouse": greenhouse, "reading": reading,
                     "online": is_recent, "alert": alert})
    return {"active_section": "invernaderos", "greenhouse_rows": rows,
            "greenhouse_total": len(rows), "greenhouse_online": online,
            "greenhouse_alerts": alerts, "greenhouse_demo_count": demo_count,
            "greenhouse_refreshed": now}


# Mediciones ficticias, no generadas por controladores. Variaciones deliberadas
# para enseñar funcionamiento del panel (no son recomendaciones agronómicas).
DEMO_PROFILES = [
    ("Jitomate", "26.4", "72.0", "61.0", 18800, "83.0", True, False),
    ("Pepino", "29.1", "81.0", "54.0", 23500, "68.0", False, True),
    ("Pimiento", "24.8", "66.0", "47.0", 16400, "91.0", False, False),
    ("Lechuga", "18.9", "87.0", "72.0", 12200, "55.0", True, False),
    ("Fresa", "36.2", "44.0", "32.0", 28600, "24.0", True, True),
]


@login_required
@require_POST
def load_greenhouse_demo(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Solo el administrador puede cargar la demostración.")
    now = timezone.now()
    with transaction.atomic():
        for index, profile in enumerate(DEMO_PROFILES, 1):
            crop, temp, hum, soil, lux, tank, irrigation, ventilation = profile
            greenhouse, _ = Greenhouse.objects.get_or_create(
                code=f"INV-{index:02d}",
                defaults={"name": f"Invernadero {index:02d}", "crop": crop, "is_demo": True},
            )
            if greenhouse.is_demo and greenhouse.crop != crop:
                greenhouse.crop = crop
                greenhouse.save(update_fields=["crop"])
            # No sustituir datos reales ni insertar demos en un equipo real.
            if not greenhouse.is_demo or greenhouse.readings.filter(is_demo=False).exists():
                continue
            GreenhouseReading.objects.filter(greenhouse=greenhouse, is_demo=True).delete()
            GreenhouseReading.objects.create(
                greenhouse=greenhouse, recorded_at=now,
                temperature=Decimal(temp), humidity=Decimal(hum),
                soil_moisture=Decimal(soil), light_lux=lux,
                tank_level=Decimal(tank), irrigation_on=irrigation,
                ventilation_on=ventilation, is_demo=True,
            )
    messages.success(request, "Lecturas ficticias cargadas para los invernaderos de demostración.")
    return redirect("/?seccion=invernaderos")
