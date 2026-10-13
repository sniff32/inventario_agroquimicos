"""Cotización y cierre de órdenes con renglones de menudeo y mayoreo combinados."""
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .inventory_services import apply_stock
from .models import Customer, Product, Sale, SaleItem, SalePayment, SaleSequence, StockBalance, StockMovement, StorageLocation


CART_KEY = "fermo_sale_cart"
CENT = Decimal("0.01")
LINE_TYPES = {Sale.RETAIL, Sale.WHOLESALE}


def empty_cart():
    return {"branch_id": None, "sale_type": Sale.RETAIL, "lines": []}


def order_type(lines):
    kinds = {line["sale_type"] for line in lines}
    return next(iter(kinds)) if len(kinds) == 1 else (Sale.MIXED if kinds else Sale.RETAIL)


def get_cart(request):
    """Compatible con carritos de sesión creados antes de implementar venta mixta."""
    data = request.session.get(CART_KEY)
    if not isinstance(data, dict):
        return empty_cart()
    legacy_type = data.get("sale_type", Sale.RETAIL)
    lines = [
        {**line, "sale_type": line.get("sale_type", legacy_type)}
        for line in data.get("lines", [])
    ]
    return {
        "branch_id": data.get("branch_id"),
        "sale_type": order_type(lines),
        "lines": lines,
    }


def save_cart(request, data):
    data["sale_type"] = order_type(data["lines"])
    request.session[CART_KEY] = data
    request.session.modified = True


def clear_cart(request):
    request.session.pop(CART_KEY, None)
    request.session.modified = True


def require_positive_int(raw, *, maximum=100000000):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("Ingresa una cantidad válida en unidades enteras.")
    if not (1 <= value <= maximum):
        raise ValidationError(f"La cantidad debe estar entre 1 y {maximum}.")
    return value


def _check_line_type(kind):
    if kind not in LINE_TYPES:
        raise ValidationError("La modalidad debe ser menudeo o mayoreo.")


def quote_line(product, sale_type, qty, *, pricing_quantity=None):
    """2% por cada 10 unidades de MAYOREO del mismo SKU (máximo 10%)."""
    pricing_quantity = qty if pricing_quantity is None else pricing_quantity
    if sale_type == Sale.WHOLESALE:
        if product.wholesale_price is None:
            raise ValidationError(f"{product.sku}: configura su precio de mayoreo primero.")
        if pricing_quantity < product.wholesale_min_qty:
            raise ValidationError(
                f"{product.sku}: el mayoreo requiere al menos "
                f"{product.wholesale_min_qty} unidades de este artículo."
            )
        base = product.wholesale_price
        percent = min((pricing_quantity // 10) * 2, 10)
    elif sale_type == Sale.RETAIL:
        base, percent = product.price, 0
    else:
        raise ValidationError("Selecciona mayoreo o menudeo.")
    base = Decimal(base).quantize(CENT)
    unit = (base * (Decimal(100 - percent) / Decimal(100))).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    gross, final = base * qty, unit * qty
    return {
        "base_unit_price": base, "discount_percent": percent,
        "unit_price": unit, "gross": gross,
        "discount_total": gross - final, "line_total": final,
    }


def get_price(product, sale_type, qty):
    return quote_line(product, sale_type, qty)["unit_price"]


def add_cart_item(request, *, branch_id, sale_type, location_id, product_id, quantity):
    """Las modalidades se eligen por renglón, pero la orden sigue siendo de una sucursal."""
    quantity = require_positive_int(quantity)
    _check_line_type(sale_type)
    loc = (
        StorageLocation.objects.select_related("branch")
        .filter(pk=location_id, branch_id=branch_id, is_active=True, branch__is_active=True)
        .first()
    )
    product = Product.objects.filter(pk=product_id, is_active=True).first()
    if not loc or not product:
        raise ValidationError("La ubicación o el producto no existe en esa sucursal.")
    current = get_cart(request)
    if current["lines"] and current["branch_id"] != loc.branch_id:
        raise ValidationError(
            "Este carrito pertenece a otra sucursal. "
            "Termínalo o vacíalo antes de cambiar de tienda."
        )
    existing = next(
        (line for line in current["lines"] if
         line["product_id"] == product.pk and line["location_id"] == loc.pk and
         line["sale_type"] == sale_type),
        None,
    )
    available = (
        StockBalance.objects.filter(product=product, location=loc)
        .values_list("quantity", flat=True).first() or 0
    )
    reserved_in_cart = sum(
        line["quantity"] for line in current["lines"]
        if line["product_id"] == product.pk and line["location_id"] == loc.pk
    )
    if quantity + reserved_in_cart > available:
        raise ValidationError(
            f"Stock insuficiente de {product.sku} en {loc}: "
            f"hay {available} unidades disponibles, y {reserved_in_cart} ya están en el carrito."
        )
    if sale_type == Sale.WHOLESALE and product.wholesale_price is None:
        raise ValidationError(f"{product.sku} todavía no tiene precio de mayoreo.")
    if existing:
        existing["quantity"] += quantity
    else:
        current["lines"].append({
            "product_id": product.pk, "location_id": loc.pk,
            "quantity": quantity, "sale_type": sale_type,
        })
    current["branch_id"] = loc.branch_id
    save_cart(request, current)


def remove_cart_item(request, index):
    data = get_cart(request)
    if not (0 <= index < len(data["lines"])):
        raise ValidationError("Renglón de carrito no encontrado.")
    data["lines"].pop(index)
    if not data["lines"]:
        data = empty_cart()
    save_cart(request, data)


def _grouped_quantities(lines):
    """Descuento por SKU mayorista; disponibilidad por ubicación en ambas modalidades."""
    wholesale_by_product = Counter()
    by_location = Counter()
    for line in lines:
        qty = require_positive_int(line["quantity"])
        _check_line_type(line["sale_type"])
        by_location[(line["product_id"], line["location_id"])] += qty
        if line["sale_type"] == Sale.WHOLESALE:
            wholesale_by_product[line["product_id"]] += qty
    return wholesale_by_product, by_location


def cart_preview(request):
    data = get_cart(request)
    lines, warnings = [], []
    gross_subtotal = discount_total = subtotal = Decimal("0.00")
    try:
        wholesale_by_product, by_location = _grouped_quantities(data["lines"])
    except ValidationError as exc:
        return {
            "branch_id": data["branch_id"], "sale_type": order_type(data["lines"]),
            "lines": [], "subtotal": subtotal, "gross_subtotal": gross_subtotal,
            "discount_total": discount_total, "warnings": exc.messages,
        }
    checked_location = set()
    for idx, entry in enumerate(data["lines"]):
        product = Product.objects.filter(pk=entry["product_id"], is_active=True).first()
        location = StorageLocation.objects.select_related("branch").filter(
            pk=entry["location_id"], is_active=True, branch__is_active=True
        ).first()
        if not product or not location or location.branch_id != data["branch_id"]:
            warnings.append(f"Renglón {idx + 1}: producto o ubicación no disponible.")
            continue
        available = StockBalance.objects.filter(
            product=product, location=location
        ).values_list("quantity", flat=True).first() or 0
        key = (product.pk, location.pk)
        if key not in checked_location and by_location[key] > available:
            warnings.append(
                f"{product.sku}: solo hay {available} unidades en {location.code}, "
                f"pero el carrito incluye {by_location[key]} entre menudeo y mayoreo."
            )
        checked_location.add(key)
        qty, kind = entry["quantity"], entry["sale_type"]
        try:
            quote = quote_line(
                product, kind, qty,
                pricing_quantity=wholesale_by_product[product.pk] if kind == Sale.WHOLESALE else qty,
            )
        except ValidationError as exc:
            warnings.extend(exc.messages)
            quote = {
                "base_unit_price": Decimal("0.00"), "discount_percent": 0,
                "unit_price": Decimal("0.00"), "gross": Decimal("0.00"),
                "discount_total": Decimal("0.00"), "line_total": Decimal("0.00"),
            }
        gross_subtotal += quote["gross"]
        discount_total += quote["discount_total"]
        subtotal += quote["line_total"]
        lines.append({
            "index": idx, "product": product, "location": location,
            "quantity": qty, "sale_type": kind,
            "sale_type_label": "Mayoreo" if kind == Sale.WHOLESALE else "Menudeo",
            "available": available, **quote,
        })
    return {
        "branch_id": data["branch_id"], "sale_type": order_type(data["lines"]),
        "lines": lines, "subtotal": subtotal, "gross_subtotal": gross_subtotal,
        "discount_total": discount_total, "warnings": warnings,
    }


@transaction.atomic
def finalize_sale(request, *, customer_name, contact="", delivery_date=None, note="", payment_term="CONTADO", due_date=None):
    """Una sola transacción para folio, renglones mixtos, stock e historial."""
    data = get_cart(request)
    if not data["lines"]:
        raise ValidationError("El carrito está vacío.")
    if not customer_name or len(customer_name.strip()) > 180:
        raise ValidationError("Indica el nombre del cliente (máximo 180 caracteres).")
    if len(contact) > 120 or len(note) > 255:
        raise ValidationError("El contacto o las observaciones son demasiado largos.")
    if payment_term not in {"CONTADO", "CREDITO"}:
        raise ValidationError("Forma de pago no válida.")
    if payment_term == "CREDITO" and due_date is None:
        raise ValidationError("Las ventas a crédito requieren fecha límite de pago.")
    if payment_term == "CREDITO" and not request.user.is_superuser:
        raise ValidationError("Solo el administrador puede autorizar ventas a crédito.")
    wholesale_by_product, qty_by_location = _grouped_quantities(data["lines"])
    # Orden estable al bloquear productos/ubicaciones, evita descuentos de último minuto.
    entries = sorted(data["lines"], key=lambda x: (
        x["product_id"], x["location_id"], x["sale_type"],
    ))
    seen = set()
    prepared = []
    for entry in entries:
        pid, lid, qty, kind = (
            entry["product_id"], entry["location_id"],
            require_positive_int(entry["quantity"]), entry["sale_type"],
        )
        key = (pid, lid, kind)
        if key in seen:
            raise ValidationError("Se detectaron renglones duplicados en el carrito.")
        seen.add(key)
        product = Product.objects.select_for_update().filter(
            pk=pid, is_active=True
        ).first()
        location = StorageLocation.objects.select_related("branch").filter(
            pk=lid, branch_id=data["branch_id"],
            is_active=True, branch__is_active=True
        ).first()
        if not product or not location:
            raise ValidationError("Algún producto o ubicación ya no está disponible.")
        quote = quote_line(
            product, kind, qty,
            pricing_quantity=wholesale_by_product[pid] if kind == Sale.WHOLESALE else qty,
        )
        prepared.append((product, location, qty, kind, quote))

    # Ambos tipos comparten las mismas unidades físicas; comprobar el total
    # ANTES de descontar para evitar ventas parciales o sobreventa.
    for pid, lid in sorted(qty_by_location):
        balance = StockBalance.objects.select_for_update().filter(
            product_id=pid, location_id=lid
        ).first()
        available = balance.quantity if balance else 0
        requested = qty_by_location[(pid, lid)]
        if requested > available:
            product = next(p for p, loc, *_ in prepared if p.pk == pid and loc.pk == lid)
            raise ValidationError(
                f"Stock insuficiente de {product.sku}: {available} disponibles "
                f"en la ubicación, {requested} solicitadas entre menudeo y mayoreo."
            )

    subtotal = sum((q["line_total"] for _, _, _, _, q in prepared), Decimal("0.00"))
    gross = sum((q["gross"] for _, _, _, _, q in prepared), Decimal("0.00"))
    kinds = {kind for _, _, _, kind, _ in prepared}
    sale_type = next(iter(kinds)) if len(kinds) == 1 else Sale.MIXED

    seq, _ = SaleSequence.objects.select_for_update().get_or_create(name="FERMO")
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    folio = f"FER-VENTA-{seq.last_number:06d}"
    customer = None
    if payment_term == "CREDITO":
        customer = Customer.objects.filter(name__iexact=customer_name.strip()).first()
        if customer is None:
            customer = Customer.objects.create(
                name=customer_name.strip(), contact=contact.strip(),
            )
    sale = Sale.objects.create(
        number=folio, sale_type=sale_type, branch_id=data["branch_id"],
        payment_term=payment_term, due_date=due_date if payment_term == "CREDITO" else None,
        customer=customer,
        customer_name=customer_name.strip(), customer_contact=contact.strip(),
        delivery_date=delivery_date or timezone.localdate(), note=note.strip(),
        subtotal=subtotal, gross_subtotal=gross, discount_total=gross - subtotal,
        created_by=request.user,
    )
    for product, location, qty, kind, quote in prepared:
        SaleItem.objects.create(
            sale=sale, product=product, location=location,
            sale_type=kind, sku_snapshot=product.sku, name_snapshot=product.name,
            quantity=qty, unit_price=quote["unit_price"],
            base_unit_price=quote["base_unit_price"],
            discount_percent=quote["discount_percent"],
            discount_total=quote["discount_total"], line_total=quote["line_total"],
        )
        apply_stock(
            product=product, location=location, actor=request.user,
            delta=-qty, kind=StockMovement.EXIT,
            note=f"Venta {folio} ({'mayoreo' if kind == Sale.WHOLESALE else 'menudeo'}): "
                 f"{sale.customer_name}"[:255],
            reference=folio,
        )
    if payment_term == "CONTADO":
        SalePayment.objects.create(
            sale=sale, amount=subtotal, recorded_by=request.user,
            reference="Cobro de contado al vender",
        )
    return sale
