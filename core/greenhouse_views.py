"""Panel de lectura de invernaderos. Sin datos reales no se afirma conectividad."""
from datetime import timedelta
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
    for greenhouse in items:
        reading = by_id.get(greenhouse.last_reading_id)
        is_recent = bool(reading and not reading.is_demo and
                         now - timedelta(minutes=5) <= reading.recorded_at <= now)
        if is_recent:
            online += 1
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
            "greenhouse_alerts": alerts, "greenhouse_refreshed": now}
