"""Vistas financieras exclusivas del administrador dentro del mismo panel FERMO."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .finance_services import collect_sale, pay_supplier, receive_purchase
from .models import Customer, Supplier


def money_redirect():
    return redirect(reverse("home") + "?seccion=finanzas")


@login_required
@require_POST
def finance_action(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Solo administración puede registrar operaciones financieras.")
    action = request.POST.get("action", "")
    try:
        if action == "supplier":
            name = request.POST.get("name", "").strip()
            if not name or len(name) > 180:
                raise ValidationError("Indica un proveedor válido.")
            if Supplier.objects.filter(name__iexact=name).exists():
                raise ValidationError("Ya existe un proveedor con ese nombre.")
            Supplier.objects.create(
                name=name, contact=request.POST.get("contact", "").strip()[:120],
                phone=request.POST.get("phone", "").strip()[:60],
            )
            messages.success(request, "Proveedor registrado correctamente.")
        elif action == "customer":
            name = request.POST.get("name", "").strip()
            if not name or len(name) > 180:
                raise ValidationError("Indica un cliente válido.")
            if Customer.objects.filter(name__iexact=name).exists():
                raise ValidationError("Ya existe un cliente con ese nombre.")
            Customer.objects.create(
                name=name, contact=request.POST.get("contact", "").strip()[:120],
                phone=request.POST.get("phone", "").strip()[:60],
            )
            messages.success(request, "Cliente registrado correctamente.")
        elif action == "purchase":
            term = request.POST.get("term", "")
            raw_due = request.POST.get("due_date", "").strip()
            due = None
            if term == "CREDITO":
                try:
                    due = date.fromisoformat(raw_due)
                except (TypeError, ValueError):
                    raise ValidationError("Indica la fecha de vencimiento de la compra a crédito.")
            purchase = receive_purchase(
                actor=request.user,
                supplier_id=request.POST.get("supplier_id"),
                product_id=request.POST.get("product_id"),
                location_id=request.POST.get("location_id"),
                quantity=request.POST.get("quantity"), unit_cost=request.POST.get("unit_cost"),
                term=term, due_date=due,
                reference=request.POST.get("reference", "").strip(),
                note=request.POST.get("note", "").strip(),
            )
            messages.success(request, f"Compra #{purchase.pk} recibida, inventario actualizado y cuenta registrada.")
        elif action == "pay":
            pay_supplier(
                actor=request.user, purchase_id=request.POST.get("purchase_id"),
                amount=request.POST.get("amount"), reference=request.POST.get("reference", "").strip(),
            )
            messages.success(request, "Abono a proveedor registrado.")
        elif action == "collect":
            collect_sale(
                actor=request.user, sale_id=request.POST.get("sale_id"),
                amount=request.POST.get("amount"), reference=request.POST.get("reference", "").strip(),
            )
            messages.success(request, "Cobro a cliente registrado.")
        else:
            raise PermissionDenied("Operación financiera no permitida.")
    except (ValidationError, ValueError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Revisa los datos del formulario.")
    return money_redirect()
