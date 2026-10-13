"""Inventario calculado por par (producto, sucursal), incluyendo existencias CERO.

Nunca usar el total corporativo para decidir si una sucursal necesita resurtido.
Los umbrales particulares prevalecen sobre el mínimo general del producto.
"""
from collections import defaultdict

from django.db.models import Sum

from .models import Branch, BranchStockMinimum, Product, StockBalance


def snapshot():
    """Resumen en consultas agrupadas; no requiere que exista una fila StockBalance."""
    products = list(
        Product.objects.filter(is_active=True)
        .values("id", "sku", "name", "min_stock")
        .order_by("name", "id")
    )
    branches = list(
        Branch.objects.filter(is_active=True)
        .values("id", "name", "code")
        .order_by("name", "id")
    )
    quantities = {
        (entry["product_id"], entry["location__branch_id"]): entry["quantity"]
        for entry in (
            StockBalance.objects.filter(
                product__is_active=True, location__branch__is_active=True
            )
            .values("product_id", "location__branch_id")
            .annotate(quantity=Sum("quantity"))
        )
    }
    overrides = {
        (item["product_id"], item["branch_id"]): item["minimum"]
        for item in BranchStockMinimum.objects.filter(
            product__is_active=True, branch__is_active=True
        ).values("product_id", "branch_id", "minimum")
    }
    by_pair = {}
    branch_alerts = defaultdict(list)
    alerts = []
    low_product_ids = set()
    for branch in branches:
        for product in products:
            key = (product["id"], branch["id"])
            qty = quantities.get(key, 0)
            minimum = overrides.get(key, product["min_stock"])
            low = qty <= minimum
            item = {
                "product_id": product["id"],
                "product_sku": product["sku"],
                "product_name": product["name"],
                "branch_id": branch["id"],
                "branch_name": branch["name"],
                "quantity": qty,
                "minimum": minimum,
                "custom_minimum": key in overrides,
                "low": low,
                "empty": qty == 0,
                "missing": max(0, minimum + 1 - qty),
            }
            by_pair[key] = item
            if low:
                alerts.append(item)
                branch_alerts[branch["id"]].append(item)
                low_product_ids.add(product["id"])
    for items in branch_alerts.values():
        items.sort(key=lambda item: (not item["empty"], item["quantity"], item["product_name"]))
    alerts.sort(key=lambda item: (not item["empty"], item["branch_name"], item["quantity"]))
    return {
        "by_pair": by_pair,
        "branches": branches,
        "products": products,
        "alerts": alerts,
        "branch_alerts": branch_alerts,
        "low_product_ids": low_product_ids,
    }


def breakdown(*, products, branches, selected_branch=None, inventory=None):
    """Presenta todas las sucursales (incluso aquellas sin registros de stock)."""
    inventory = inventory or snapshot()
    focus = [selected_branch] if selected_branch is not None else list(branches)
    ids = [product.pk for product in products]
    locations = defaultdict(list)
    if ids:
        for balance in (
            StockBalance.objects.filter(
                product_id__in=ids,
                location__branch__is_active=True,
            )
            .select_related("location__branch")
            .order_by("location__branch__name", "location__code")
        ):
            locations[(balance.product_id, balance.location.branch_id)].append({
                "name": balance.location.code,
                "description": balance.location.description,
                "quantity": balance.quantity,
            })
    result = []
    for product in products:
        store_list = []
        lows = 0
        for store in focus:
            record = inventory["by_pair"].get((product.pk, store.pk))
            if not record:
                continue
            if record["low"]:
                lows += 1
            store_list.append({
                **record,
                "locations": locations[(product.pk, store.pk)],
            })
        result.append({
            "product": product,
            "stores": store_list,
            "low_count": lows,
            "has_alert": lows > 0,
        })
    return result
