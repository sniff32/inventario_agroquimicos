"""Deterministic, clearly fictional greenhouse telemetry; not a physical control feed."""
import math
from datetime import timedelta
from django.utils import timezone

PROFILES = [
    ("INV-01", "Jitomate", 25.7, 73, 62, 82, 0.4),
    ("INV-02", "Pepino", 27.1, 79, 55, 67, 1.5),
    ("INV-03", "Pimiento", 24.2, 68, 49, 89, 2.7),
    ("INV-04", "Lechuga", 21.3, 82, 70, 53, 3.4),
    ("INV-05", "Fresa", 30.8, 54, 37, 37, 4.5),
]


def _clip(v, low, high):
    return round(max(low, min(high, v)), 1)


def sample(profile, when):
    code, crop, temp, humidity, soil, tank, phase = profile
    minute = int(when.timestamp() // 60)
    hour = when.hour + when.minute / 60
    daylight = max(0, math.sin(math.pi * (hour - 6) / 12))
    cycle = math.sin(minute / 36 + phase)
    ripple = math.sin(minute / 11 + phase * 2) * 0.35
    irrigation = (minute + int(phase * 12)) % 95 < 12
    ventilation = temp + daylight * 4 + cycle * 1.5 > 28
    temperature = _clip(temp - 2.0 + daylight * 4.8 + cycle * 1.3 + ripple, 7, 45)
    if code == "INV-05" and 11 <= hour <= 17:
        temperature = _clip(temperature + 4.1, 7, 45)
    rh = _clip(humidity + math.sin(minute / 49 + phase) * 5 - daylight * 6 + (2 if irrigation else 0), 20, 99)
    ground = _clip(soil + math.sin(minute / 85 + phase) * 7 + (7 if irrigation else 0), 10, 100)
    light = round((daylight ** 1.4) * (28000 + phase * 1900))
    tank_level = _clip(tank - (minute % 240) / 55 + math.sin(minute / 130 + phase) * 1.5, 5, 100)
    return {
        "at": when.isoformat(), "temperature": temperature, "humidity": rh,
        "soil_moisture": ground, "light_lux": light, "tank_level": tank_level,
        "irrigation_on": irrigation, "ventilation_on": ventilation,
    }


def simulation_snapshot():
    now = timezone.localtime(timezone.now())
    # A 24h window at 15-minute intervals; generated deterministically from time.
    end_minute = now.replace(second=0, microsecond=0)
    series = []
    for profile in PROFILES:
        values = [sample(profile, end_minute - timedelta(minutes=15 * i)) for i in range(96, -1, -1)]
        current = sample(profile, now)
        temperatures = [v["temperature"] for v in values]
        humidities = [v["humidity"] for v in values]
        alerts = []
        if current["temperature"] > 35:
            alerts.append("Temperatura alta")
        if current["tank_level"] < 30:
            alerts.append("Tanque bajo")
        series.append({
            "code": profile[0], "crop": profile[1], "current": current,
            "history": values, "alerts": alerts,
            "stats": {
                "temp_min": min(temperatures), "temp_max": max(temperatures),
                "temp_avg": round(sum(temperatures) / len(temperatures), 1),
                "humidity_avg": round(sum(humidities) / len(humidities), 1),
            },
        })
    return {"mode": "simulation", "generated_at": now.isoformat(), "interval_seconds": 30, "greenhouses": series}
