from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class SmokeTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")

    def test_login_page_accessible(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_home_requires_authentication(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, "/cuentas/ingresar/?next=/")

    def test_authenticated_user_can_view_home(self):
        user = get_user_model().objects.create_user(
            username="usuario_prueba",
            password="SoloParaPrueba123!",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel principal")

    def test_bootstrap_admin_creates_first_account_only(self):
        from unittest.mock import patch
        from django.core.management import call_command

        with patch.dict(
            "os.environ",
            {
                "DJANGO_SUPERUSER_USERNAME": "admin_pruebas",
                "DJANGO_SUPERUSER_EMAIL": "admin@example.com",
                "DJANGO_SUPERUSER_PASSWORD": "ClavePruebasLarga!2026#Qx7",
            },
        ):
            call_command("bootstrap_admin")
            call_command("bootstrap_admin")

        User = get_user_model()
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)
        admin = User.objects.get(username="admin_pruebas")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.check_password("ClavePruebasLarga!2026#Qx7"))


class UserManagementTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="ClaveLargaAdmin!2026"
        )
        self.employee = User.objects.create_user(
            username="empleado", email="empleado@example.com", password="ClaveLargaEmpleado!2026"
        )
        self.manage_url = reverse("manage_users")
        self.admin_url = reverse("home") + "?seccion=administracion"

    def test_admin_sees_management_inside_dashboard(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.admin_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usuarios y accesos")
        self.assertContains(response, "Crear usuario")

    def test_employee_does_not_see_management_menu(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Crear usuario")
        self.assertNotContains(response, "Administración de Django")
        self.assertEqual(self.client.get(self.admin_url).status_code, 403)

    def test_employee_cannot_create_users_via_post(self):
        self.client.force_login(self.employee)
        response = self.client.post(self.manage_url, {
            "action": "create", "username": "intruso",
            "email": "intruso@example.com",
            "role": "Administrador",
            "password1": "ContrasenaValidaFuerte!2026",
            "password2": "ContrasenaValidaFuerte!2026",
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="intruso").exists())

    def test_post_without_login_redirects(self):
        response = self.client.post(self.manage_url, {"action": "create"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/cuentas/ingresar/"))

    def test_create_employee_and_hash_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.manage_url, {
            "action": "create",
            "username": "nuevo_empleado",
            "first_name": "Nuevo",
            "last_name": "Empleado",
            "email": "nuevo@example.com",
            "role": "Empleado",
            "password1": "ClaveSegura!2026ABCxyz",
            "password2": "ClaveSegura!2026ABCxyz",
        })
        self.assertRedirects(response, self.admin_url)
        account = get_user_model().objects.get(username="nuevo_empleado")
        self.assertFalse(account.is_superuser)
        self.assertFalse(account.is_staff)
        self.assertTrue(account.is_active)
        self.assertTrue(account.groups.filter(name="Empleado").exists())
        self.assertTrue(account.check_password("ClaveSegura!2026ABCxyz"))
        self.assertNotEqual(account.password, "ClaveSegura!2026ABCxyz")

    def test_admin_can_create_another_administrator(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.manage_url, {
            "action": "create", "username": "admin_dos",
            "email": "admin_dos@example.com", "role": "Administrador",
            "password1": "ClaveSegura!2026ABCxyz",
            "password2": "ClaveSegura!2026ABCxyz",
        })
        self.assertEqual(response.status_code, 302)
        second = get_user_model().objects.get(username="admin_dos")
        self.assertTrue(second.is_superuser)
        self.assertTrue(second.is_staff)

    def test_common_password_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.manage_url, {
            "action": "create", "username": "inseguro",
            "email": "inseguro@example.com", "role": "Invitado",
            "password1": "password123",
            "password2": "password123",
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(username="inseguro").exists())

    def test_reset_password_and_suspend_employee(self):
        self.client.force_login(self.admin)
        password_response = self.client.post(self.manage_url, {
            "action": "password", "user_id": str(self.employee.pk),
            "new_password1": "ClaveNuevaFuerte!2026",
            "new_password2": "ClaveNuevaFuerte!2026",
        })
        self.assertEqual(password_response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.check_password("ClaveNuevaFuerte!2026"))
        status_response = self.client.post(self.manage_url, {
            "action": "status", "user_id": str(self.employee.pk)
        })
        self.assertEqual(status_response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

    def test_role_change_to_guest(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.manage_url, {
            "action": "role", "user_id": str(self.employee.pk),
            "role": "Invitado",
        })
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.groups.filter(name="Invitado").exists())
        self.assertFalse(self.employee.is_superuser)

    def test_cannot_suspend_or_demote_self(self):
        self.client.force_login(self.admin)
        for action, other in [("status", {}), ("role", {"role": "Invitado"})]:
            response = self.client.post(self.manage_url, {
                "action": action, "user_id": str(self.admin.pk), **other
            })
            self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.is_superuser)

    def test_missing_or_malformed_user_id_returns_not_found(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.manage_url, {
            "action": "status", "user_id": "no-numero"
        })
        self.assertEqual(response.status_code, 404)
