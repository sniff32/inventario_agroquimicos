"""Pruebas de inventario de abarrotes, pagos y autorización financiera."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError

from .demo import DEMO_PRODUCTS, load_demo
from .finance_services import balance_due, collect_sale, pay_supplier, receive_purchase
from .inventory_services import apply_stock
from .models import (
    Branch, Customer, Product, Purchase, PurchasePayment, Sale, SalePayment,
    StockBalance, StockMovement, StorageLocation, Supplier,
)


class GroceryDemoTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            "warehouse_admin", "admin@fermo.example", "TestStrong!Warehouse2026"
        )

    def test_demo_has_50_grocery_products_single_warehouse_and_is_idempotent(self):
        old_branch = Branch.objects.create(code="DEMO-T02", name="Tienda Norte", is_demo=True)
        old_loc = StorageLocation.objects.create(branch=old_branch, code="Repisa A")
        old = Product.objects.create(
            sku="DEMO-020", name="Cable USB tipo B", is_demo=True, price=45, cost=19
        )
        apply_stock(
            product=old, location=old_loc, delta=4, actor=self.admin,
            kind=StockMovement.DEMO, reference="DEMO-2026",
        )
        self.assertEqual(len(DEMO_PRODUCTS), 50)
        created, moved = load_demo(actor=self.admin)
        self.assertEqual(created, 50)
        self.assertEqual(moved, 50)
        self.assertEqual(Product.objects.filter(is_active=True, sku__startswith="ABR-").count(), 50)
        self.assertFalse(Product.objects.get(pk=old.pk).is_active)
        self.assertFalse(Branch.objects.get(pk=old_branch.pk).is_active)
        self.assertEqual(StockMovement.objects.filter(product=old).count(), 1)
        self.assertEqual(Branch.objects.filter(is_active=True).count(), 1)
        self.assertEqual(StockBalance.objects.filter(
            product__sku__startswith="ABR-", quantity__gt=0
        ).count(), 50)
        self.assertEqual(load_demo(actor=self.admin), (0, 0))
        self.assertEqual(StockMovement.objects.filter(reference="ABARROTES-DEMO").count(), 50)
        self.assertEqual(self.client.login(username="warehouse_admin", password="TestStrong!Warehouse2026"), True)
        page = self.client.get(reverse("home"), {"seccion": "productos"})
        self.assertContains(page, "Arroz blanco")
        self.assertNotContains(page, "Cable USB tipo B")
        self.assertContains(page, "ABR-001")

    def test_product_editor_uses_dialog_not_table_expanding_details(self):
        load_demo(actor=self.admin)
        self.client.force_login(self.admin)
        page = self.client.get(reverse("home"), {"seccion": "productos"})
        self.assertContains(page, "catalog-edit-dialog")
        self.assertContains(page, ".showModal()")
        self.assertContains(page, "fermo-edit-")

    def test_conversion_migration_retires_old_demo_without_deleting_history(self):
        """Reproduce la conversión del despliegue sobre una base con demostración anterior."""
        from importlib import import_module
        from django.apps import apps
        legacy_branch = Branch.objects.create(
            code="DEMO-CENTRAL", name="Almacén viejo", is_demo=True
        )
        legacy_loc = StorageLocation.objects.create(
            branch=legacy_branch, code="Estante electrónico"
        )
        legacy = Product.objects.create(
            sku="DEMO-003", name="Capacitor de prueba", is_demo=True,
            price=4, cost=2
        )
        apply_stock(
            product=legacy, location=legacy_loc, delta=15,
            actor=self.admin, kind=StockMovement.DEMO,
            reference="DEMO-2026",
        )
        convert = import_module("core.migrations.0008_convert_legacy_demo").migrate_existing_demo
        convert(apps, None)
        legacy.refresh_from_db()
        legacy_branch.refresh_from_db()
        self.assertFalse(legacy.is_active)
        self.assertFalse(legacy_branch.is_active)
        self.assertEqual(Product.objects.filter(
            is_active=True, sku__startswith="ABR-"
        ).count(), 50)
        self.assertEqual(StockMovement.objects.filter(product=legacy).count(), 1)
        convert(apps, None)
        self.assertEqual(StockMovement.objects.filter(
            reference="ABARROTES-DEMO"
        ).count(), 50)

    def test_cannot_create_another_branch(self):
        load_demo(actor=self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("inventory_action"), {
            "action": "branch", "return_to": "sucursales",
            "code": "NUEVA", "name": "Otra sucursal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Branch.objects.filter(code="NUEVA").exists())


class FinanceFlowTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            "finance_admin", "fadmin@fermo.example", "TestStrong!Finance2026"
        )
        self.employee = get_user_model().objects.create_user(
            "seller", password="TestStrong!Employee2026"
        )
        self.employee.groups.add(Group.objects.get_or_create(name="Empleado")[0])
        self.supplier = Supplier.objects.create(name="Proveedor del Valle")
        self.warehouse = Branch.objects.create(code="FERMO-ALMACEN", name="Almacén FERMO")
        self.location = StorageLocation.objects.create(branch=self.warehouse, code="Pasillo A")
        self.product = Product.objects.create(
            sku="ABR-123", name="Aceite vegetal 900 ml", cost=Decimal("30.00"),
            price=Decimal("49.00"), wholesale_price=Decimal("40.00"), wholesale_min_qty=10
        )
        self.client.force_login(self.admin)

    def receive(self, term="CREDITO", reference="FACT-100"):
        return receive_purchase(
            actor=self.admin, supplier_id=self.supplier.pk,
            product_id=self.product.pk, location_id=self.location.pk,
            quantity=20, unit_cost="34.50", term=term,
            due_date=date(2026, 10, 30) if term == "CREDITO" else None,
            reference=reference,
        )

    def test_credit_purchase_increases_stock_and_creates_payable(self):
        purchase = self.receive()
        self.assertEqual(purchase.total, Decimal("690.00"))
        self.assertEqual(balance_due(purchase), Decimal("690.00"))
        self.assertEqual(
            StockBalance.objects.get(product=self.product, location=self.location).quantity, 20
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.cost, Decimal("34.50"))
        move = StockMovement.objects.get(reference=f"COMPRA-{purchase.pk}")
        self.assertEqual((move.before, move.after), (0, 20))
        pay_supplier(actor=self.admin, purchase_id=purchase.pk, amount="200.00")
        self.assertEqual(balance_due(purchase), Decimal("490.00"))
        pay_supplier(actor=self.admin, purchase_id=purchase.pk, amount="490.00")
        self.assertEqual(balance_due(purchase), Decimal("0.00"))
        with self.assertRaises(ValidationError):
            pay_supplier(actor=self.admin, purchase_id=purchase.pk, amount="1.00")

    def test_cash_purchase_is_fully_paid_and_duplicate_invoice_rejected(self):
        purchase = self.receive(term="CONTADO")
        self.assertEqual(balance_due(purchase), Decimal("0.00"))
        self.assertEqual(PurchasePayment.objects.get(purchase=purchase).amount, Decimal("690.00"))
        with self.assertRaises(ValidationError):
            self.receive(term="CONTADO")
        self.assertEqual(StockBalance.objects.get(
            product=self.product, location=self.location
        ).quantity, 20)

    def test_finance_dashboard_requires_superuser(self):
        page = self.client.get(reverse("home"), {"seccion": "finanzas"})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Cuentas por pagar")
        self.assertContains(page, "Recepción de mercancía")
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse("home"), {"seccion": "finanzas"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("finance_action"), {
            "action": "supplier", "name": "Proveedor X",
        }).status_code, 403)

    def test_finance_credit_sale_keeps_single_folio_and_unpaid_balance(self):
        self.receive()
        self.client.force_login(self.admin)
        bal = StockBalance.objects.get(product=self.product, location=self.location)
        self.client.post(reverse("sale_action"), {
            "action": "add", "sale_type": "MENUDEO",
            "balance_id": bal.pk, "quantity": 2,
        })
        sale_resp = self.client.post(reverse("sale_action"), {
            "action": "checkout", "customer_name": "Abarrotes Esmeralda",
            "customer_contact": "555-333", "delivery_date": "2026-10-15",
            "payment_term": "CREDITO", "due_date": "2026-10-22",
        })
        self.assertEqual(sale_resp.status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.customer.name, "Abarrotes Esmeralda")
        self.assertEqual(sale.payment_term, "CREDITO")
        self.assertEqual(sale.subtotal, Decimal("98.00"))
        self.assertEqual(balance_due(sale), Decimal("98.00"))
        self.assertFalse(SalePayment.objects.exists())
        collect_sale(actor=self.admin, sale_id=sale.pk, amount="30.00")
        self.assertEqual(balance_due(sale), Decimal("68.00"))
        with self.assertRaises(ValidationError):
            collect_sale(actor=self.admin, sale_id=sale.pk, amount="68.01")
        collect_sale(actor=self.admin, sale_id=sale.pk, amount="68.00")
        self.assertEqual(balance_due(sale), Decimal("0.00"))
        self.assertEqual(StockBalance.objects.get(
            product=self.product, location=self.location
        ).quantity, 18)

    def test_cash_sale_is_collected_automatically(self):
        self.receive()
        bal = StockBalance.objects.get(product=self.product, location=self.location)
        self.client.post(reverse("sale_action"), {
            "action": "add", "sale_type": "MENUDEO", "balance_id": bal.pk, "quantity": 1
        })
        self.client.post(reverse("sale_action"), {
            "action": "checkout", "customer_name": "Abarrotes Luna",
            "delivery_date": "2026-10-16", "payment_term": "CONTADO",
        })
        sale = Sale.objects.get()
        self.assertEqual(sale.payment_term, "CONTADO")
        self.assertEqual(balance_due(sale), Decimal("0.00"))
        self.assertEqual(SalePayment.objects.get(sale=sale).amount, sale.subtotal)

    def test_employee_cannot_authorize_credit(self):
        self.receive()
        bal = StockBalance.objects.get(product=self.product, location=self.location)
        self.client.force_login(self.employee)
        self.client.post(reverse("sale_action"), {
            "action": "add", "sale_type": "MENUDEO", "balance_id": bal.pk, "quantity": 1
        })
        self.client.post(reverse("sale_action"), {
            "action": "checkout", "customer_name": "Abarrotes Sol",
            "delivery_date": "2026-10-16", "payment_term": "CREDITO",
            "due_date": "2026-10-26",
        })
        self.assertFalse(Sale.objects.exists())
        self.assertEqual(StockBalance.objects.get(
            product=self.product, location=self.location
        ).quantity, 20)
