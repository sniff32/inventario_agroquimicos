from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone
from .greenhouse_simulation import PROFILES, sample, simulation_snapshot


class GreenhouseSimulationTests(TestCase):
    def test_five_distinct_profiles_and_historical_data(self):
        data = simulation_snapshot()
        self.assertEqual(data["mode"], "simulation")
        self.assertEqual(len(data["greenhouses"]), 5)
        self.assertEqual(len({g["code"] for g in data["greenhouses"]}), 5)
        for house in data["greenhouses"]:
            self.assertEqual(len(house["history"]), 97)
            self.assertGreaterEqual(house["current"]["humidity"], 0)
            self.assertLessEqual(house["current"]["tank_level"], 100)

    def test_values_change_with_time_and_are_repeatable(self):
        base = timezone.now()
        one = sample(PROFILES[0], base)
        self.assertEqual(one, sample(PROFILES[0], base))
        later = sample(PROFILES[0], base + timedelta(minutes=42))
        self.assertNotEqual(one["temperature"], later["temperature"])

    def test_endpoint_requires_login(self):
        response = Client().get("/invernaderos/simulacion/")
        self.assertEqual(response.status_code, 302)

    def test_authenticated_endpoint_is_explicit_demo(self):
        user = get_user_model().objects.create_user(username="sim_user", password="sim_pw_123!")
        client = Client()
        client.force_login(user)
        response = client.get("/invernaderos/simulacion/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "simulation")
        self.assertEqual(response["Cache-Control"], "no-store")
