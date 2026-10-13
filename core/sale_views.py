"""Vistas de venta en la misma aplicación de Inventario Empresarial."""
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse
from django.views.decorators.http import require_POST

from .inventory_views import can_move
from .models import Branch, Sale, StockBalance
from .sale_services import (
    add_cart_item, cart_preview, clear_cart, finalize_sale, get_cart,
    remove_cart_item, require_positive_int,
)


def sales_context(request):
    cart = cart_preview(request)
    sales = Sale.objects.select_related("branch", "created_by")
    if not (request.user.is_superuser and request.GET.get("historicas") == "1"):
        sales = sales.filter(items__product__is_active=True).distinct()
    term = request.GET.get("buscar", "").strip()[:100]
    if term:
        sales = sales.filter(Q(number__icontains=term) | Q(customer_name__icontains=term))
    selected = None
    raw = request.GET.get("ver", "").strip()
    if raw:
        if not raw.isdecimal():
            raise Http404("Venta no encontrada")
        selected = get_object_or_404(
            Sale.objects.select_related("branch", "created_by").prefetch_related(
                "items__location", "items__product"
            ), pk=int(raw),
        )
    return {
        "active_section": "ventas",
        "sales_cart": cart,
        "raw_cart_lines": get_cart(request)["lines"],
        "sales_rows": sales[:70],
        "sales_query": term,
        "sales_archived": request.GET.get("historicas") == "1" and request.user.is_superuser,
        "sale_selected": selected,
        "sales_branches": Branch.objects.filter(is_active=True),
        "sale_today": timezone.localdate().isoformat(),
        "cart_branch_name": (Branch.objects.filter(pk=cart["branch_id"])
                             .values_list("name", flat=True).first() if cart["branch_id"] else ""),
    }


def _sales_redirect():
    return redirect(reverse("home") + "?seccion=ventas")


@login_required
@require_POST
def sale_action(request):
    if not can_move(request.user):
        raise PermissionDenied("Solo administradores y empleados pueden registrar ventas.")
    action = request.POST.get("action", "")
    try:
        if action == "add":
            balance_id = require_positive_int(request.POST.get("balance_id"))
            balance = get_object_or_404(
                StockBalance.objects.select_related("product", "location__branch"),
                pk=balance_id,
                quantity__gt=0, product__is_active=True,
                location__is_active=True, location__branch__is_active=True,
            )
            add_cart_item(
                request, branch_id=balance.location.branch_id,
                sale_type=request.POST.get("sale_type", Sale.RETAIL),
                location_id=balance.location_id,
                product_id=balance.product_id,
                quantity=request.POST.get("quantity"),
            )
            messages.success(request, "Artículo agregado al carrito.")
        elif action == "remove":
            idx = request.POST.get("index", "")
            if not idx.isdecimal():
                raise ValidationError("Índice de renglón inválido.")
            remove_cart_item(request, int(idx))
            messages.success(request, "Producto quitado del carrito.")
        elif action == "clear":
            clear_cart(request)
            messages.success(request, "Carrito vaciado; no se realizó ninguna venta.")
        elif action == "checkout":
            value = request.POST.get("delivery_date", "")
            try:
                parsed = date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValidationError("Indica una fecha válida de salida / entrega.")
            credit_date = request.POST.get("due_date", "").strip()
            credit_due = None
            if request.POST.get("payment_term", "CONTADO") == "CREDITO":
                try:
                    credit_due = date.fromisoformat(credit_date)
                except (TypeError, ValueError):
                    raise ValidationError("El crédito requiere una fecha de vencimiento válida.")
            sale = finalize_sale(
                request,
                customer_name=request.POST.get("customer_name", "").strip(),
                contact=request.POST.get("customer_contact", "").strip(),
                delivery_date=parsed,
                note=request.POST.get("note", "").strip(),
                payment_term=request.POST.get("payment_term", "CONTADO"),
                due_date=credit_due,
            )
            clear_cart(request)
            messages.success(request, f"Venta {sale.number} confirmada. Existencias descontadas.")
            return redirect(reverse("home") + f"?seccion=ventas&ver={sale.pk}")
        else:
            raise PermissionDenied("Operación no reconocida.")
    except ValidationError as e:
        messages.error(request, "; ".join(str(v) for v in e.messages))
    return _sales_redirect()


@login_required
def sale_docx(request, sale_id):
    if not can_move(request.user):
        raise PermissionDenied("Solo personal autorizado puede descargar órdenes de venta.")
    sale = get_object_or_404(
        Sale.objects.select_related("branch", "created_by").prefetch_related(
            "items__location"
        ), pk=sale_id,
    )
    from .sale_document import build_sale_docx
    data = build_sale_docx(sale)
    response = HttpResponse(
        data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    response["Content-Disposition"] = f'attachment; filename="{sale.number}.docx"'
    response["Cache-Control"] = "private, no-store"
    return response
