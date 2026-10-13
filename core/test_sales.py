"""Pruebas de carrito, mayorista, folios, auditoría y Word corporativo."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .inventory_services import apply_stock
from .models import Branch, Product, Sale, SaleItem, StockBalance, StockMovement, StorageLocation


class SalesFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="administrador_prueba", email="administrador@example.com",
            password="ClaveSeguraDePrueba2026!Larga",
        )
        self.employee = User.objects.create_user(
            username="empleado_ventas", password="ClaveEmpleadoVentas2026!Larga"
        )
        self.guest = User.objects.create_user(
            username="invitado_ventas", password="ClaveInvitadoVentas2026!Larga"
        )
        self.employee.groups.add(Group.objects.get_or_create(name="Empleado")[0])
        self.guest.groups.add(Group.objects.get_or_create(name="Invitado")[0])
        self.branch = Branch.objects.create(code="FER-01", name="Sucursal FERMO Centro")
        self.other = Branch.objects.create(code="FER-02", name="Sucursal FERMO Norte")
        self.loc = StorageLocation.objects.create(branch=self.branch, code="Repisa 2")
        self.other_loc = StorageLocation.objects.create(branch=self.other, code="Repisa 3")
        self.p1 = Product.objects.create(
            sku="SENSOR-001", name="Sensor electrónico", price="100.00",
            wholesale_price="78.50", wholesale_min_qty=5,
        )
        self.p2 = Product.objects.create(
            sku="CABLE-002", name="Cable USB tipo B", price="50.00",
            wholesale_price="35.00", wholesale_min_qty=3,
        )
        apply_stock(
            product=self.p1, location=self.loc, delta=30, actor=self.admin,
            kind=StockMovement.ENTRY,
        )
        apply_stock(
            product=self.p2, location=self.loc, delta=20, actor=self.admin,
            kind=StockMovement.ENTRY,
        )
        apply_stock(
            product=self.p1, location=self.other_loc, delta=4, actor=self.admin,
            kind=StockMovement.ENTRY,
        )
        self.balance1 = StockBalance.objects.get(product=self.p1, location=self.loc)
        self.balance2 = StockBalance.objects.get(product=self.p2, location=self.loc)
        self.other_balance = StockBalance.objects.get(product=self.p1, location=self.other_loc)
        self.client.force_login(self.employee)

    def add(self, balance, qty, sale_type="MENUDEO"):
        return self.client.post(reverse("sale_action"), {
            "action": "add", "balance_id": str(balance.pk),
            "quantity": str(qty), "sale_type": sale_type,
        })

    def checkout(self, customer="Cliente de prueba"):
        return self.client.post(reverse("sale_action"), {
            "action": "checkout", "customer_name": customer,
            "customer_contact": "contacto@example.com",
            "delivery_date": "2026-10-15", "note": "Entregar en mostrador",
        })

    def test_menu_and_login_use_fermo_brand(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "fermo-logo")
        self.assertContains(response, "Ventas y órdenes")
        self.assertContains(response, "Sistema de inventarios y ventas")
        self.assertEqual(self.client.get(reverse("home"), {"seccion": "ventas"}).status_code, 200)

    def test_retail_multi_item_one_order_one_folio_full_stock_audit_and_word(self):
        self.assertEqual(self.add(self.balance1, 2).status_code, 302)
        self.assertEqual(self.add(self.balance2, 3).status_code, 302)
        self.assertEqual(Sale.objects.count(), 0)
        response = self.client.get(reverse("home"), {"seccion": "ventas"})
        self.assertContains(response, "Carrito de la orden")
        self.assertContains(response, "350,00" if False else "350")
        saved = self.checkout("Ferretería Cliente")
        self.assertEqual(saved.status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.number, "FER-VENTA-000001")
        self.assertEqual(sale.customer_name, "Ferretería Cliente")
        self.assertEqual(sale.sale_type, Sale.RETAIL)
        self.assertEqual(sale.subtotal, Decimal("350.00"))
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(sale.delivery_date, date(2026, 10, 15))
        self.assertEqual(set(sale.items.values_list("unit_price", flat=True)), {Decimal("100"), Decimal("50")})
        self.balance1.refresh_from_db()
        self.balance2.refresh_from_db()
        self.assertEqual((self.balance1.quantity, self.balance2.quantity), (28, 17))
        rows = StockMovement.objects.filter(reference=sale.number)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(sum(x.delta for x in rows), -5)
        self.assertTrue(all(x.actor == self.employee and x.kind == StockMovement.EXIT for x in rows))
        page = self.client.get(reverse("home"), {"seccion": "ventas", "ver": sale.pk})
        self.assertContains(page, "Ferretería Cliente")
        self.assertContains(page, sale.number)
        word = self.client.get(reverse("sale_docx", args=[sale.pk]))
        self.assertEqual(word.status_code, 200)
        self.assertTrue(word.content.startswith(b"PK"))
        with ZipFile(BytesIO(word.content)) as z:
            self.assertIn("word/document.xml", z.namelist())
            self.assertTrue(any(name.startswith("word/media/") for name in z.namelist()))
            doc_xml = z.read("word/document.xml").decode()
            self.assertIn("Ferretería Cliente", doc_xml)
            self.assertIn("FER-VENTA-000001", doc_xml)
        self.assertEqual(self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]["lines"], [])

    def test_wholesale_uses_tier_and_minimum_per_product(self):
        self.assertEqual(self.add(self.balance1, 5, "MAYOREO").status_code, 302)
        self.assertEqual(self.add(self.balance2, 3, "MAYOREO").status_code, 302)
        self.assertEqual(self.checkout().status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.sale_type, Sale.WHOLESALE)
        self.assertEqual(sale.subtotal, Decimal("497.50"))
        self.assertEqual(set(sale.items.values_list("unit_price", flat=True)), {Decimal("78.50"), Decimal("35.00")})

    def test_below_wholesale_threshold_is_rejected_without_stock_change(self):
        self.add(self.balance1, 2, "MAYOREO")
        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sale.objects.count(), 0)
        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.quantity, 30)
        page = self.client.get(reverse("home"), {"seccion": "ventas"})
        self.assertContains(page, "requiere al menos")

    def test_rejects_cross_branch_but_allows_both_modes_same_branch(self):
        self.add(self.balance1, 2, "MENUDEO")
        self.add(self.other_balance, 1, "MENUDEO")
        self.add(self.balance2, 1, "MAYOREO")
        page = self.client.get(reverse("home"), {"seccion": "ventas"})
        self.assertEqual(len(page.context["sales_cart"]["lines"]), 2)
        self.assertEqual(page.context["sales_cart"]["sale_type"], Sale.MIXED)
        self.assertContains(page, "Este carrito pertenece a otra sucursal")

    def test_availability_rechecked_at_checkout_and_atomic(self):
        self.add(self.balance1, 30)
        self.add(self.balance2, 5)
        apply_stock(
            product=self.p1, location=self.loc, delta=-1, actor=self.admin,
            kind=StockMovement.EXIT, note="Otra salida confirmada",
        )
        self.checkout()
        self.assertFalse(Sale.objects.exists())
        self.balance2.refresh_from_db()
        self.assertEqual(self.balance2.quantity, 20)
        self.assertEqual(StockMovement.objects.filter(reference__startswith="FER-VENTA").count(), 0)

    def test_folios_successivos_and_snapshot_of_price(self):
        self.add(self.balance1, 1)
        self.checkout()
        self.add(self.balance2, 1)
        self.checkout("Otro cliente")
        self.assertEqual(
            list(Sale.objects.order_by("number").values_list("number", flat=True)),
            ["FER-VENTA-000001", "FER-VENTA-000002"],
        )
        self.p1.price = Decimal("999.00")
        self.p1.save(update_fields=["price"])
        self.assertEqual(SaleItem.objects.get(sale__number="FER-VENTA-000001").unit_price, Decimal("100.00"))

    def test_guest_cannot_access_sales_or_download(self):
        self.add(self.balance1, 1)
        self.checkout()
        sale = Sale.objects.get()
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(reverse("home"), {"seccion": "ventas"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("sale_action"), {"action": "clear"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("sale_docx", args=[sale.pk])).status_code, 403)
        page = self.client.get(reverse("home"))
        self.assertNotContains(page, "Ventas y órdenes")

    def test_admin_can_edit_wholesale_price_through_product_form(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("inventory_action"), {
            "action": "edit_product", "return_to": "productos",
            "product_id": self.p1.pk, "sku": self.p1.sku,
            "name": self.p1.name, "brand": "", "unit": "pieza",
            "price": "100.00", "wholesale_price": "74.25",
            "wholesale_min_qty": "8", "cost": "0", "min_stock": "5",
        })
        self.assertEqual(response.status_code, 302)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.wholesale_price, Decimal("74.25"))
        self.assertEqual(self.p1.wholesale_min_qty, 8)


    def test_wholesale_tier_math_and_maximum_discount(self):
        from .sale_services import quote_line
        cases = [
            (10, 2, Decimal("76.93")),
            (19, 2, Decimal("76.93")),
            (20, 4, Decimal("75.36")),
            (30, 6, Decimal("73.79")),
            (40, 8, Decimal("72.22")),
            (50, 10, Decimal("70.65")),
            (100, 10, Decimal("70.65")),
        ]
        for quantity, percent, unit in cases:
            with self.subTest(quantity=quantity):
                q = quote_line(self.p1, Sale.WHOLESALE, quantity)
                self.assertEqual(q["discount_percent"], percent)
                self.assertEqual(q["base_unit_price"], Decimal("78.50"))
                self.assertEqual(q["unit_price"], unit)
                self.assertEqual(q["discount_total"], q["gross"] - q["line_total"])

    def test_wholesale_20_units_persists_all_discounts_and_docx(self):
        self.assertEqual(self.add(self.balance1, 20, "MAYOREO").status_code, 302)
        preview = self.client.get(reverse("home"), {"seccion": "ventas"})
        self.assertEqual(preview.context["sales_cart"]["discount_total"], Decimal("62.80"))
        self.assertEqual(self.checkout().status_code, 302)
        sale = Sale.objects.get()
        item = sale.items.get()
        self.assertEqual(sale.gross_subtotal, Decimal("1570.00"))
        self.assertEqual(sale.discount_total, Decimal("62.80"))
        self.assertEqual(sale.subtotal, Decimal("1507.20"))
        self.assertEqual(item.discount_percent, 4)
        self.assertEqual(item.base_unit_price, Decimal("78.50"))
        self.assertEqual(item.unit_price, Decimal("75.36"))
        self.assertEqual(item.discount_total, Decimal("62.80"))
        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.quantity, 10)
        word = self.client.get(reverse("sale_docx", args=[sale.pk]))
        with ZipFile(BytesIO(word.content)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
            self.assertIn("Descuento por volumen", xml)
            self.assertIn("TOTAL FINAL", xml)
            self.assertIn("4%", xml)

    def test_search_and_detail_return_stock_and_other_branches(self):
        resp = self.client.get(reverse("sale_search"), {"q": "SENSOR-001"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"]
        self.assertEqual(len(data), 2)
        self.assertIn("30", str([item["quantity"] for item in data]))
        self.assertTrue(all(item["sku"] == "SENSOR-001" for item in data))
        response = self.client.get(reverse("sale_product_detail", args=[self.balance1.pk]))
        self.assertEqual(response.status_code, 200)
        details = response.json()
        self.assertEqual(details["available"], 30)
        self.assertEqual(details["location"], "Repisa 2")
        self.assertEqual(details["retail_price"], "100.00")
        self.assertEqual(details["wholesale_price"], "78.50")
        self.assertEqual(details["wholesale_min_qty"], 5)
        self.assertEqual(len(details["branches"]), 2)
        self.assertEqual(sorted(row["quantity"] for row in details["branches"]), [4, 30])

    def test_guest_cannot_query_sale_prices(self):
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(reverse("sale_search"), {"q": "SENSOR"}).status_code, 403)
        self.assertEqual(self.client.get(
            reverse("sale_product_detail", args=[self.balance1.pk])
        ).status_code, 403)

    def test_inspector_and_search_script_render_for_employee(self):
        page = self.client.get(reverse("home"), {"seccion": "ventas"})
        self.assertContains(page, "sale-product-search")
        self.assertContains(page, "sale-product-info")
        self.assertContains(page, "sale-search-results")
        self.assertContains(page, "sale-cart-raw")
        self.assertContains(page, "sales.")


    def test_same_sku_from_two_shelves_receives_single_volume_tier(self):
        other_shelf = StorageLocation.objects.create(
            branch=self.branch, code="Bodega superior"
        )
        apply_stock(
            product=self.p1, location=other_shelf, delta=10,
            actor=self.admin, kind=StockMovement.ENTRY,
        )
        other_balance = StockBalance.objects.get(product=self.p1, location=other_shelf)
        self.assertEqual(self.add(self.balance1, 5, "MAYOREO").status_code, 302)
        self.assertEqual(self.add(other_balance, 5, "MAYOREO").status_code, 302)
        preview = self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]
        self.assertEqual(preview["subtotal"], Decimal("769.30"))
        self.assertEqual(preview["discount_total"], Decimal("15.70"))
        self.assertEqual(self.checkout().status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual(sale.subtotal, Decimal("769.30"))
        self.assertTrue(all(row.discount_percent == 2 for row in sale.items.all()))

    def test_cannot_sell_more_stock_than_selected_shelf(self):
        resp = self.add(self.other_balance, 5, "MENUDEO")
        self.assertEqual(resp.status_code, 302)
        page = self.client.get(reverse("home"), {"seccion": "ventas"})
        self.assertContains(page, "Stock insuficiente")
        self.assertEqual(page.context["sales_cart"]["lines"], [])


    def test_mixed_sale_same_order_folio_and_word(self):
        """Un producto mayorista + un extra minorista usan el mismo folio."""
        self.add(self.balance1, 10, "MAYOREO")
        self.add(self.balance2, 2, "MENUDEO")
        preview = self.client.get(reverse("home"), {"seccion": "ventas"})
        cart = preview.context["sales_cart"]
        self.assertEqual(cart["sale_type"], Sale.MIXED)
        self.assertEqual(cart["subtotal"], Decimal("869.30"))  # 10 × 76.93 + 2 × 50
        self.assertEqual(len(cart["lines"]), 2)
        self.assertContains(preview, "Mixta")
        self.assertEqual(self.checkout("Cliente mixto").status_code, 302)
        sale = Sale.objects.get()
        self.assertEqual(sale.sale_type, Sale.MIXED)
        self.assertEqual(sale.subtotal, Decimal("869.30"))
        self.assertEqual(set(sale.items.values_list("sale_type", flat=True)), {
            Sale.RETAIL, Sale.WHOLESALE,
        })
        self.assertEqual(
            sorted(StockMovement.objects.filter(reference=sale.number)
                   .values_list("delta", flat=True)), [-10, -2],
        )
        self.balance1.refresh_from_db()
        self.balance2.refresh_from_db()
        self.assertEqual((self.balance1.quantity, self.balance2.quantity), (20, 18))
        response = self.client.get(reverse("sale_docx", args=[sale.pk]))
        with ZipFile(BytesIO(response.content)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("Mixta", xml)
            self.assertIn("Mayoreo", xml)
            self.assertIn("Menudeo", xml)

    def test_same_product_same_shelf_both_modes_cannot_overdraw_stock(self):
        self.assertEqual(self.add(self.balance1, 20, "MAYOREO").status_code, 302)
        self.assertEqual(self.add(self.balance1, 10, "MENUDEO").status_code, 302)
        self.assertEqual(self.add(self.balance1, 1, "MENUDEO").status_code, 302)
        cart = self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]
        self.assertEqual(len(cart["lines"]), 2)
        self.assertEqual(cart["warnings"], [])
        self.assertEqual(self.checkout().status_code, 302)
        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.quantity, 0)
        self.assertEqual(StockMovement.objects.filter(
            reference=Sale.objects.get().number
        ).count(), 2)

    def test_mixed_cart_rejects_total_stock_overrun_after_parallel_exit(self):
        self.add(self.balance1, 20, "MAYOREO")
        self.add(self.balance1, 10, "MENUDEO")
        apply_stock(
            product=self.p1, location=self.loc, delta=-1, actor=self.admin,
            kind=StockMovement.EXIT, note="Otra venta confirmada",
        )
        self.assertEqual(self.checkout().status_code, 302)
        self.assertFalse(Sale.objects.exists())
        self.balance1.refresh_from_db()
        self.assertEqual(self.balance1.quantity, 29)
        self.assertFalse(StockMovement.objects.filter(reference__startswith="FER-VENTA").exists())

    def test_retail_units_do_not_count_towards_wholesale_discount_tier(self):
        """8 mayoreo + 5 menudeo no alcanzan el mínimo de 10 para mayoreo."""
        self.p1.wholesale_min_qty = 10
        self.p1.save(update_fields=["wholesale_min_qty"])
        self.add(self.balance1, 8, "MAYOREO")
        self.add(self.balance1, 5, "MENUDEO")
        cart = self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]
        self.assertEqual(cart["sale_type"], Sale.MIXED)
        self.assertTrue(any("requiere al menos" in w for w in cart["warnings"]))
        self.checkout()
        self.assertFalse(Sale.objects.exists())
        self.add(self.balance1, 2, "MAYOREO")
        self.assertEqual(self.checkout().status_code, 302)
        sale = Sale.objects.get()
        wholesale = sale.items.get(sale_type=Sale.WHOLESALE)
        retail = sale.items.get(sale_type=Sale.RETAIL)
        self.assertEqual(wholesale.quantity, 10)
        self.assertEqual(wholesale.discount_percent, 2)
        self.assertEqual(retail.quantity, 5)
        self.assertEqual(retail.discount_percent, 0)

    def test_legacy_wholesale_cart_preserves_line_type(self):
        session = self.client.session
        session["fermo_sale_cart"] = {
            "branch_id": self.branch.pk,
            "sale_type": Sale.WHOLESALE,
            "lines": [{"product_id": self.p1.pk, "location_id": self.loc.pk, "quantity": 5}],
        }
        session.save()
        cart = self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]
        self.assertEqual(cart["sale_type"], Sale.WHOLESALE)
        self.assertEqual(cart["lines"][0]["sale_type"], Sale.WHOLESALE)
        self.assertEqual(self.checkout().status_code, 302)
        self.assertEqual(Sale.objects.get().items.get().sale_type, Sale.WHOLESALE)

    def test_below_wholesale_minimum_can_be_completed_using_multiple_locations(self):
        self.p1.wholesale_min_qty = 10
        self.p1.save(update_fields=["wholesale_min_qty"])
        shelf = StorageLocation.objects.create(branch=self.branch, code="Bodega 5")
        apply_stock(
            product=self.p1, location=shelf, delta=6, actor=self.admin,
            kind=StockMovement.ENTRY,
        )
        other_balance = StockBalance.objects.get(product=self.p1, location=shelf)
        self.add(self.balance1, 5, "MAYOREO")
        first = self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]
        self.assertTrue(first["warnings"])
        self.add(other_balance, 5, "MAYOREO")
        ready = self.client.get(reverse("home"), {"seccion": "ventas"}).context["sales_cart"]
        self.assertFalse(ready["warnings"])
        self.assertEqual(ready["subtotal"], Decimal("769.30"))
        self.assertEqual(self.checkout().status_code, 302)
        self.assertEqual(Sale.objects.get().items.count(), 2)
