"""Operaciones financieras simples, auditadas y atómicas para abarrotes.

Ingresos: cobros de ventas. Egresos: pagos a proveedores.
La utilidad y la caja no equivalen al total de ventas: son métricas distintas.
"""
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .inventory_services import apply_stock
from .models import (
    Customer, Product, Purchase, PurchasePayment, Sale, SalePayment,
    StockMovement, StorageLocation, Supplier,
)

CENT = Decimal("0.01")


def read_money(raw, *, positive=True):
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Importe monetario inválido.")
    if not value.is_finite() or value.as_tuple().exponent < -2 or value > Decimal("999999999999.99"):
        raise ValidationError("Indica un importe válido con máximo dos decimales.")
    if value <= 0 if positive else value < 0:
        raise ValidationError("El importe debe ser positivo." if positive else "El importe no puede ser negativo.")
    return value.quantize(CENT)


def read_qty(raw):
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("La cantidad debe ser entera y positiva.")
    if qty < 1 or qty > 100000000:
        raise ValidationError("Cantidad fuera de rango.")
    return qty


def balance_due(document):
    paid = document.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    return document.total - paid if isinstance(document, Purchase) else document.subtotal - paid


@transaction.atomic
def receive_purchase(*, actor, supplier_id, product_id, location_id, quantity,
                     unit_cost, term, due_date=None, reference="", note=""):
    """Una recepción recibe stock y crea la deuda en la misma transacción."""
    if term not in {Purchase.CASH, Purchase.CREDIT}:
        raise ValidationError("Elige compra de contado o crédito.")
    if term == Purchase.CREDIT and due_date is None:
        raise ValidationError("La compra a crédito requiere fecha de vencimiento.")
    qty = read_qty(quantity)
    cost = read_money(unit_cost)
    if len(reference) > 80 or len(note) > 255:
        raise ValidationError("Referencia u observaciones demasiado largas.")
    supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first()
    product = Product.objects.select_for_update().filter(pk=product_id, is_active=True).first()
    location = StorageLocation.objects.select_related("branch").filter(
        pk=location_id, branch__is_active=True, is_active=True,
        branch__code="FERMO-ALMACEN",
    ).first()
    if not supplier or not product or not location:
        raise ValidationError("Selecciona proveedor, artículo y ubicación activos del almacén FERMO.")
    if reference and Purchase.objects.filter(
        supplier=supplier, reference=reference.strip(), product=product, location=location
    ).exists():
        raise ValidationError("Ya se registró este producto de la factura para esa ubicación.")
    total = cost * qty
    if total > Decimal("999999999999.99"):
        raise ValidationError("El total excede el máximo permitido.")
    purchase = Purchase.objects.create(
        supplier=supplier, product=product, location=location,
        quantity=qty, unit_cost=cost, total=total, term=term,
        due_date=due_date if term == Purchase.CREDIT else None,
        reference=reference.strip(), note=note.strip(), created_by=actor,
    )
    apply_stock(
        product=product, location=location, delta=qty,
        actor=actor, kind=StockMovement.ENTRY,
        note=f"Compra proveedor {supplier.name}"[:255],
        reference=f"COMPRA-{purchase.pk}",
    )
    product.cost = cost
    product.save(update_fields=["cost"])
    if term == Purchase.CASH:
        PurchasePayment.objects.create(
            purchase=purchase, amount=total, recorded_by=actor,
            reference="Pago de contado al recibir",
        )
    return purchase


@transaction.atomic
def pay_supplier(*, actor, purchase_id, amount, reference=""):
    purchase = Purchase.objects.select_for_update().filter(pk=purchase_id).first()
    if not purchase:
        raise ValidationError("Compra no encontrada.")
    value = read_money(amount)
    due = balance_due(purchase)
    if value > due:
        raise ValidationError(f"El saldo pendiente de esta compra es ${due:.2f}.")
    return PurchasePayment.objects.create(
        purchase=purchase, amount=value, recorded_by=actor, reference=reference[:80],
    )


@transaction.atomic
def collect_sale(*, actor, sale_id, amount, reference=""):
    sale = Sale.objects.select_for_update().filter(pk=sale_id).first()
    if not sale or sale.payment_term == "SIN_CLASIFICAR":
        raise ValidationError("Esta venta no tiene una cuenta por cobrar registrada.")
    value = read_money(amount)
    due = balance_due(sale)
    if value > due:
        raise ValidationError(f"El saldo pendiente de esta venta es ${due:.2f}.")
    return SalePayment.objects.create(
        sale=sale, amount=value, recorded_by=actor, reference=reference[:80],
    )


def financial_context():
    """Las ventas antiguas sin términos nunca se suponen cobradas ni adeudadas."""
    purchases = list(
        Purchase.objects.select_related("supplier", "product", "created_by")
        .prefetch_related("payments").order_by("-created_at")
    )
    sales = list(
        Sale.objects.exclude(payment_term="SIN_CLASIFICAR")
        .select_related("customer", "created_by").prefetch_related("payments")
        .order_by("-created_at")
    )
    for doc in purchases + sales:
        doc.balance = balance_due(doc)
        doc.paid = (doc.total if isinstance(doc, Purchase) else doc.subtotal) - doc.balance
    return {
        "purchases": purchases, "finance_sales": sales,
        "payables": [p for p in purchases if p.balance > 0],
        "receivables": [s for s in sales if s.balance > 0],
        "accounts_payable": sum((p.balance for p in purchases), Decimal("0.00")),
        "accounts_receivable": sum((s.balance for s in sales), Decimal("0.00")),
        "cash_received": SalePayment.objects.aggregate(v=Sum("amount"))["v"] or Decimal("0.00"),
        "cash_paid": PurchasePayment.objects.aggregate(v=Sum("amount"))["v"] or Decimal("0.00"),
        "suppliers": Supplier.objects.filter(is_active=True),
        "customers": Customer.objects.filter(is_active=True),
        "buyable_products": Product.objects.filter(is_active=True).order_by("name")[:250],
        "warehouse_locations": StorageLocation.objects.filter(
            is_active=True, branch__is_active=True, branch__code="FERMO-ALMACEN"
        ).order_by("code"),
        "unclassified_sales": Sale.objects.filter(payment_term="SIN_CLASIFICAR").count(),
    }
