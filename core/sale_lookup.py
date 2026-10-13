"""Búsqueda dinámica de existencias; responde solo a usuarios con permiso de ventas."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .inventory_views import can_move
from .models import Branch, BranchStockMinimum, StockBalance


@login_required
@require_GET
def search_sale_products(request):
    if not can_move(request.user):
        raise PermissionDenied("No tienes acceso a ventas.")
    query = request.GET.get("q", "").strip()[:90]
    qs = StockBalance.objects.filter(
        quantity__gt=0, product__is_active=True,
        location__is_active=True, location__branch__is_active=True,
    ).select_related("product__category", "location__branch")
    if query:
        qs = qs.filter(
            Q(product__sku__icontains=query) |
            Q(product__name__icontains=query) |
            Q(product__brand__icontains=query) |
            Q(product__category__name__icontains=query)
        )
    rows = qs.order_by("product__name", "location__branch__name", "location__code")[:35]
    return JsonResponse({"results": [{
        "balance_id": bal.pk,
        "location_id": bal.location_id,
        "product_id": bal.product_id,
        "sku": bal.product.sku,
        "product": bal.product.name,
        "brand": bal.product.brand,
        "category": bal.product.category.name if bal.product.category_id else "Sin categoría",
        "branch_id": bal.location.branch_id,
        "branch": bal.location.branch.name,
        "location": bal.location.code,
        "quantity": bal.quantity,
        "unit": bal.product.unit,
        "retail_price": str(bal.product.price),
        "wholesale_price": str(bal.product.wholesale_price) if bal.product.wholesale_price is not None else None,
        "wholesale_min_qty": bal.product.wholesale_min_qty,
        "min_stock": bal.product.min_stock,
    } for bal in rows]})


@login_required
@require_GET
def sale_product_detail(request, balance_id):
    if not can_move(request.user):
        raise PermissionDenied("No tienes acceso a ventas.")
    selected = get_object_or_404(
        StockBalance.objects.select_related("product", "location__branch"),
        pk=balance_id, product__is_active=True,
        location__is_active=True, location__branch__is_active=True,
    )
    stock_by_branch = {}
    for bal in (
        StockBalance.objects.filter(
            product_id=selected.product_id,
            location__branch__is_active=True,
        ).select_related("location__branch")
    ):
        id = bal.location.branch_id
        stock_by_branch[id] = stock_by_branch.get(id, 0) + bal.quantity
    custom_minimum = BranchStockMinimum.objects.filter(
        product_id=selected.product_id,
        branch_id=selected.location.branch_id,
    ).values_list("minimum", flat=True).first()
    shops = [{
        "name": b.name,
        "quantity": stock_by_branch.get(b.pk, 0),
        "selected": b.pk == selected.location.branch_id,
    } for b in Branch.objects.filter(is_active=True).order_by("name")]
    return JsonResponse({
        "balance_id": selected.pk, "location_id": selected.location_id,
        "product_id": selected.product_id,
        "product": selected.product.name, "sku": selected.product.sku,
        "brand": selected.product.brand, "unit": selected.product.unit,
        "branch_id": selected.location.branch_id, "branch": selected.location.branch.name,
        "location": selected.location.code,
        "available": selected.quantity,
        "retail_price": str(selected.product.price),
        "wholesale_price": str(selected.product.wholesale_price) if selected.product.wholesale_price is not None else None,
        "wholesale_min_qty": selected.product.wholesale_min_qty,
        "min_stock": custom_minimum if custom_minimum is not None else selected.product.min_stock,
        "branches": shops,
    })
