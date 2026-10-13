"""Pruebas del inventario que también renderizan las páginas reales."""
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .demo import load_demo
from .inventory_services import apply_stock
from .models import Branch, Product, StockBalance, StockMovement, StorageLocation


class InventoryFlowTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="dueño", password="ClaveAdminSegura!2026", email="due@example.com"
        )
        self.employee = get_user_model().objects.create_user(
            username="empleado2", password="ClaveEmpleadoSegura!2026"
        )
        self.guest = get_user_model().objects.create_user(
            username="invitado2", password="ClaveInvitadoSegura!2026"
        )
        employee_group, _ = Group.objects.get_or_create(name="Empleado")
        guest_group, _ = Group.objects.get_or_create(name="Invitado")
        self.employee.groups.add(employee_group)
        self.guest.groups.add(guest_group)
        self.branch1 = Branch.objects.create(code="T1", name="Tienda Centro")
        self.branch2 = Branch.objects.create(code="T2", name="Tienda Norte")
        self.loc1 = StorageLocation.objects.create(branch=self.branch1, code="Repisa 1")
        self.loc2 = StorageLocation.objects.create(branch=self.branch2, code="Repisa 2")
        self.product = Product.objects.create(sku="PRUEBA-001", name="Sensor de prueba")

    def test_inventory_sections_render_without_errors(self):
        self.client.force_login(self.admin)
        for section in ("panel", "productos", "sucursales", "movimientos", "historial"):
            response = self.client.get(reverse("home"), {"seccion": section})
            self.assertEqual(response.status_code, 200, section)

    def test_guest_only_reads_and_cannot_post_stock(self):
        self.client.force_login(self.guest)
        self.assertEqual(
            self.client.get(reverse("home"), {"seccion": "productos"}).status_code, 200
        )
        response = self.client.post(reverse("inventory_action"), {
            "action": "stock", "product_id": self.product.pk, "location_id": self.loc1.pk,
            "kind": "ENTRADA", "quantity": 10
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(StockMovement.objects.exists())

    def test_employee_can_receive_and_sell_and_audit(self):
        self.client.force_login(self.employee)
        url = reverse("inventory_action")
        response = self.client.post(url, {
            "action": "stock", "return_to": "movimientos",
            "product_id": self.product.pk, "location_id": self.loc1.pk,
            "kind": "ENTRADA", "quantity": 25, "note": "Recepción de proveedor"
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.post(url, {
            "action": "stock", "return_to": "movimientos",
            "product_id": self.product.pk, "location_id": self.loc1.pk,
            "kind": "SALIDA", "quantity": 4, "note": "Venta mostrador"
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            StockBalance.objects.get(product=self.product, location=self.loc1).quantity, 21
        )
        movements = list(StockMovement.objects.order_by("pk"))
        self.assertEqual([(m.before, m.delta, m.after) for m in movements],
                         [(0, 25, 25), (25, -4, 21)])
        self.assertTrue(all(m.actor == self.employee for m in movements))
        self.assertContains(
            self.client.get(reverse("home"), {"seccion": "historial"}), "Venta mostrador"
        )

    def test_cannot_sell_more_than_available(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("inventory_action"), {
            "action": "stock", "return_to": "movimientos",
            "product_id": self.product.pk, "location_id": self.loc1.pk,
            "kind": "SALIDA", "quantity": 6, "note": "Venta"
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Existencias insuficientes")
        self.assertFalse(StockMovement.objects.exists())

    def test_adjustment_records_before_after(self):
        self.client.force_login(self.employee)
        apply_stock(
            product=self.product, location=self.loc1, actor=self.admin,
            delta=12, kind=StockMovement.ENTRY,
        )
        response = self.client.post(reverse("inventory_action"), {
            "action": "stock", "return_to": "movimientos",
            "product_id": self.product.pk, "location_id": self.loc1.pk,
            "kind": "AJUSTE", "quantity": 7, "note": "Conteo físico"
        })
        self.assertEqual(response.status_code, 302)
        move = StockMovement.objects.latest("pk")
        self.assertEqual((move.before, move.delta, move.after), (12, -5, 7))

    def test_transfer_logs_both_legs(self):
        self.client.force_login(self.admin)
        apply_stock(
            product=self.product, location=self.loc1, actor=self.admin,
            delta=20, kind=StockMovement.ENTRY,
        )
        response = self.client.post(reverse("inventory_action"), {
            "action": "transfer", "return_to": "movimientos",
            "product_id": self.product.pk,
            "origin_id": self.loc1.pk, "destination_id": self.loc2.pk,
            "quantity": 6, "note": "Reabastecer Norte",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            StockBalance.objects.get(product=self.product, location=self.loc1).quantity, 14
        )
        self.assertEqual(
            StockBalance.objects.get(product=self.product, location=self.loc2).quantity, 6
        )
        pair = list(StockMovement.objects.exclude(reference=""))
        self.assertEqual(len(pair), 2)
        self.assertEqual({m.delta for m in pair}, {-6, 6})
        self.assertEqual(len({m.reference for m in pair}), 1)

    def test_demo_is_explicit_and_repeatable(self):
        self.client.force_login(self.admin)
        self.assertEqual(Product.objects.count(), 1)
        url = reverse("inventory_action")
        for _ in range(2):
            response = self.client.post(url, {"action": "demo", "return_to": "panel"})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Product.objects.filter(is_demo=True, sku__startswith="ABR-").count(), 50)
        self.assertEqual(Branch.objects.filter(is_demo=True).count(), 1)
        self.assertEqual(StockMovement.objects.filter(kind="DEMO", reference="ABARROTES-DEMO").count(), 50)

    def test_import_xlsx_sets_final_stock_and_registers_changes(self):
        self.client.force_login(self.admin)
        book = Workbook()
        sheet = book.active
        sheet.append(["codigo", "nombre", "sucursal", "ubicacion", "cantidad", "precio"])
        sheet.append(["PRUEBA-001", "Sensor de prueba", "Tienda Centro", "Repisa 1", 8, 55])
        buffer = BytesIO()
        book.save(buffer)
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile(
            "inventario.xlsx", buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(reverse("inventory_action"), {
            "action": "import", "return_to": "productos", "archivo": upload,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StockBalance.objects.get(product=self.product, location=self.loc1).quantity, 8)
        self.assertEqual(StockMovement.objects.get(kind="IMPORTACION").actor, self.admin)
        template_response = self.client.get(reverse("inventory_template"))
        self.assertEqual(template_response.status_code, 200)
        self.assertIn(b"PK", template_response.content[:4])

    def test_employee_cannot_import_or_create_product(self):
        self.client.force_login(self.employee)
        for action in ("import", "product", "demo", "branch"):
            response = self.client.post(reverse("inventory_action"), {"action": action})
            self.assertEqual(response.status_code, 403)


class BranchStockAlertTests(TestCase):
    """Un gran total corporativo no elimina las alertas de las demás tiendas."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="admin_alertas", email="alertas@example.com",
            password="ClaveAdminFuerte!2026",
        )
        self.worker = get_user_model().objects.create_user(
            username="empleado_alertas", password="ClaveEmpleadoFuerte!2026"
        )
        self.guest = get_user_model().objects.create_user(
            username="invitado_alertas", password="ClaveInvitadoFuerte!2026"
        )
        group, _ = Group.objects.get_or_create(name="Empleado")
        self.worker.groups.add(group)
        self.north = Branch.objects.create(code="NORTE", name="Norte")
        self.south = Branch.objects.create(code="SUR", name="Sur")
        self.center = Branch.objects.create(code="CENTRO", name="Centro")
        self.north_shelf = StorageLocation.objects.create(
            branch=self.north, code="Local 2 / Repisa 2"
        )
        self.center_shelf = StorageLocation.objects.create(branch=self.center, code="Mostrador")
        self.center_back = StorageLocation.objects.create(branch=self.center, code="Bodega")
        self.product = Product.objects.create(
            sku="SENSOR-ALERTA", name="Sensor de temperatura",
            min_stock=10
        )
        # Norte tiene 2, Centro tiene 200 y Sur tiene 0 unidades y ninguna fila.
        apply_stock(
            product=self.product, location=self.north_shelf, delta=2,
            actor=self.admin, kind=StockMovement.ENTRY
        )
        apply_stock(
            product=self.product, location=self.center_shelf, delta=70,
            actor=self.admin, kind=StockMovement.ENTRY
        )
        apply_stock(
            product=self.product, location=self.center_back, delta=130,
            actor=self.admin, kind=StockMovement.ENTRY
        )
        self.client.force_login(self.admin)

    def test_dashboard_counts_two_branch_alerts_despite_202_company_units(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count_units"], 202)
        self.assertEqual(response.context["count_low"], 2)
        self.assertEqual(response.context["count_low_products"], 1)
        summaries = {b.code: b for b in response.context["branch_rows"]}
        self.assertEqual(summaries["CENTRO"].low_count, 0)
        self.assertEqual(summaries["NORTE"].low_count, 1)
        self.assertEqual(summaries["SUR"].low_count, 1)
        self.assertContains(response, "Reposición por sucursal")
        self.assertContains(response, "Agotado")

    def test_expands_every_branch_with_shelf_and_zero_quantity(self):
        response = self.client.get(reverse("home"), {"seccion": "productos"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ver ubicaciones")
        self.assertContains(response, "Local 2 / Repisa 2")
        self.assertContains(response, "Mostrador")
        self.assertContains(response, "Bodega")
        self.assertContains(response, "Sin unidades registradas en esta sucursal")
        self.assertContains(response, "2 alertas")

    def test_branch_filter_only_checks_that_branch(self):
        response = self.client.get(reverse("home"), {
            "seccion": "productos", "sucursal": str(self.center.pk),
            "solo_bajo": "1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 0)
        response = self.client.get(reverse("home"), {
            "seccion": "productos", "sucursal": str(self.north.pk),
            "solo_bajo": "1",
        })
        self.assertEqual(len(response.context["products"]), 1)
        self.assertEqual(response.context["products"][0]["stores"][0]["quantity"], 2)

    def test_custom_minimum_per_branch_changes_alerts_without_stock_movement(self):
        from .models import BranchStockMinimum
        before_movements = StockMovement.objects.count()
        response = self.client.post(reverse("inventory_action"), {
            "action": "store_minimum",
            "return_to": "productos",
            "product_id": self.product.pk,
            "branch_id": self.north.pk,
            "minimum": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BranchStockMinimum.objects.get(
            product=self.product, branch=self.north
        ).minimum, 1)
        self.assertEqual(StockMovement.objects.count(), before_movements)
        dashboard = self.client.get(reverse("home"))
        self.assertEqual(dashboard.context["count_low"], 1)
        self.assertEqual(dashboard.context["low_alerts"][0]["branch_name"], "Sur")

    def test_clearing_custom_minimum_restores_general_minimum(self):
        from .models import BranchStockMinimum
        BranchStockMinimum.objects.create(
            branch=self.north, product=self.product, minimum=1
        )
        response = self.client.post(reverse("inventory_action"), {
            "action": "store_minimum",
            "return_to": "productos", "product_id": self.product.pk,
            "branch_id": self.north.pk, "minimum": "",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BranchStockMinimum.objects.exists())
        self.assertEqual(self.client.get(reverse("home")).context["count_low"], 2)

    def test_guest_and_employee_cannot_change_minima(self):
        for user in (self.guest, self.worker):
            self.client.force_login(user)
            response = self.client.post(reverse("inventory_action"), {
                "action": "store_minimum", "product_id": self.product.pk,
                "branch_id": self.north.pk, "minimum": "0",
            })
            self.assertEqual(response.status_code, 403)
        from .models import BranchStockMinimum
        self.assertEqual(BranchStockMinimum.objects.count(), 0)

    def test_stock_change_recalculates_alert_by_shop(self):
        self.client.force_login(self.worker)
        response = self.client.post(reverse("inventory_action"), {
            "action": "stock", "return_to": "movimientos",
            "product_id": self.product.pk,
            "location_id": self.north_shelf.pk,
            "quantity": "20", "kind": StockMovement.ENTRY,
            "note": "Reabastecimiento Norte",
        })
        self.assertEqual(response.status_code, 302)
        dashboard = self.client.get(reverse("home"))
        self.assertEqual(dashboard.context["count_low"], 1)
        self.assertEqual(
            next(b.low_count for b in dashboard.context["branch_rows"] if b.code == "NORTE"), 0
        )
