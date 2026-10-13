"""Páginas y acciones de inventario dentro del mismo panel principal."""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .demo import load_demo
from .excel_import import excel_template, import_excel
from .forms import BranchForm, CategoryForm, LocationForm, ProductForm
from .inventory_services import apply_stock, transfer_stock
from .models import Branch, BranchStockMinimum, Category, Product, Sale, StockBalance, StockMovement, StorageLocation
from .stock_alerts import breakdown, snapshot

SECTIONS = {"panel", "productos", "sucursales", "movimientos", "historial", "ventas", "finanzas"}


def can_move(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="Empleado").exists()
    )


def page_url(section):
    return reverse("home") + "?seccion=" + section


def _selected_branch(request):
    raw = request.GET.get("sucursal", "")
    if not raw.isdecimal():
        return None
    return Branch.objects.filter(pk=int(raw)).first()


def inventory_context(request, section):
    branches = Branch.objects.filter(is_active=True)
    # Una sola operación comercial. Las sucursales viejas permanecen para auditoría.
    if branches.filter(code="AGRO-ALMACEN").exists():
        branches = branches.filter(code="AGRO-ALMACEN")
    locations = StorageLocation.objects.select_related("branch").filter(
        is_active=True, branch__in=branches
    )
    products_base = Product.objects.filter(is_active=True)
    branch = _selected_branch(request)
    if branch is None or not branches.filter(pk=branch.pk).exists():
        branch = branches.first() if branches.count() == 1 else None
    report = snapshot() if section in {"panel", "productos", "sucursales"} else None
    context = {
        "active_section": section,
        "branches": branches,
        "locations": locations,
        "categories": Category.objects.exclude(name__in=["Componentes", "Semiconductores", "Sensores", "Módulos", "Microcontroladores", "Redes", "Fuentes", "Cables"]),
        "available_products": products_base.order_by("name"),
        "can_move": can_move(request.user),
        "can_manage_catalog": request.user.is_superuser,
        "selected_branch": branch,
    }

    if section == "panel":
        context.update({
            "count_products": products_base.count(),
            "count_branches": branches.count(),
            "count_units": StockBalance.objects.filter(
                product__is_active=True, location__branch__in=branches
            ).aggregate(
                total=Coalesce(Sum("quantity"), Value(0), output_field=IntegerField())
            )["total"],
            "count_movements": StockMovement.objects.filter(
                product__is_active=True, location__branch__in=branches
            ).count(),
            "count_sales": Sale.objects.filter(items__product__is_active=True).distinct().count(),
            "sales_amount": Sale.objects.aggregate(value=Sum("subtotal"))["value"] or Decimal("0.00"),
            "count_low": len(report["alerts"]),
            "count_low_products": len(report["low_product_ids"]),
            "low_alerts": report["alerts"][:12],
            "branches_with_alerts": sum(bool(report["branch_alerts"].get(b.pk)) for b in branches),
            "recent_movements": StockMovement.objects.select_related(
                "product", "location__branch", "actor"
            ).filter(product__is_active=True, location__branch__in=branches)[:8],
            "branch_rows": branches.annotate(
                units=Coalesce(
                    Sum("locations__balances__quantity"),
                    Value(0), output_field=IntegerField()
                )
            ),
            "demo_available": not products_base.filter(is_demo=True, sku__startswith="AGR-").exists(),
        })
        for b in context["branch_rows"]:
            b.low_count = len(report["branch_alerts"].get(b.pk, []))
            b.empty_count = sum(item["empty"] for item in report["branch_alerts"].get(b.pk, []))
            b.low_examples = report["branch_alerts"].get(b.pk, [])[:3]

    elif section == "productos":
        q = request.GET.get("q", "").strip()[:100]
        qs = products_base.select_related("category")
        if branch:
            qs = qs.annotate(
                total_qty=Coalesce(
                    Sum("balances__quantity", filter=Q(
                        balances__location__branch=branch
                    )), Value(0), output_field=IntegerField()
                )
            )
        else:
            qs = qs.annotate(
                total_qty=Coalesce(Sum("balances__quantity"), Value(0), output_field=IntegerField())
            )
        if q:
            qs = qs.filter(Q(sku__icontains=q) | Q(name__icontains=q) | Q(brand__icontains=q))
        low_only = request.GET.get("solo_bajo") == "1"
        if low_only:
            low_ids = {
                pid for (pid, bid), item in report["by_pair"].items()
                if item["low"] and (branch is None or branch.pk == bid)
            }
            qs = qs.filter(pk__in=low_ids)
        page_products = list(qs.order_by("name")[:200])
        context.update({
            "products": breakdown(
                products=page_products, branches=branches,
                selected_branch=branch, inventory=report
            ),
            "low_only": low_only,
            "search_query": q,
            "product_form": ProductForm(),
            "category_form": CategoryForm(),
            "demo_available": not products_base.filter(is_demo=True).exists(),
        })

    elif section == "sucursales":
        context.update({
            "branch_rows": branches.annotate(
                units=Coalesce(
                    Sum("locations__balances__quantity"), Value(0), output_field=IntegerField()
                ),
                location_count=Count("locations", distinct=True),
            ),
            "branch_form": BranchForm(),
            "location_form": LocationForm(),
            "location_rows": locations[:150],
        })
        for b in context["branch_rows"]:
            b.low_count = len(report["branch_alerts"].get(b.pk, []))
            b.empty_count = sum(item["empty"] for item in report["branch_alerts"].get(b.pk, []))

    elif section == "movimientos":
        balances = StockBalance.objects.select_related(
            "product", "location__branch"
        ).filter(quantity__gt=0, product__is_active=True, location__branch__in=branches)
        if branch:
            balances = balances.filter(location__branch=branch)
        context.update({
            "stock_rows": balances.order_by("-updated_at")[:100],
            "movement_kinds": [
                (StockMovement.ENTRY, "Entrada (recepción)"),
                (StockMovement.EXIT, "Salida (uso, merma u otra)"),
                (StockMovement.ADJUST, "Ajuste a cantidad exacta"),
            ],
        })

    elif section == "historial":
        history = StockMovement.objects.select_related(
            "product", "location__branch", "actor"
        )
        if not (request.user.is_superuser and request.GET.get("archivados") == "1"):
            history = history.filter(product__is_active=True)
        if branch:
            history = history.filter(location__branch=branch)
        raw_actor = request.GET.get("usuario", "")
        if raw_actor.isdecimal():
            history = history.filter(actor_id=int(raw_actor))
        kind = request.GET.get("tipo", "")
        if kind in {val for val, _label in StockMovement.TYPES}:
            history = history.filter(kind=kind)
        q = request.GET.get("q", "").strip()[:80]
        if q:
            history = history.filter(Q(product__sku__icontains=q) | Q(product__name__icontains=q))
        for key, lookup in (("desde", "created_at__date__gte"), ("hasta", "created_at__date__lte")):
            raw_date = request.GET.get(key, "")
            if raw_date:
                try:
                    history = history.filter(**{lookup: date.fromisoformat(raw_date)})
                except ValueError:
                    pass
        context.update({
            "history_rows": history[:250],
            "history_archived": request.GET.get("archivados") == "1" and request.user.is_superuser,
            "history_types": StockMovement.TYPES,
            "history_users": get_user_model().objects.order_by("username"),
            "history_query": q,
            "history_user": raw_actor,
            "history_kind": kind,
            "history_start": request.GET.get("desde", ""),
            "history_end": request.GET.get("hasta", ""),
        })
    return context


def _get_id(raw):
    return _read_positive(raw)


def _read_positive(raw):
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("Ingresa una cantidad entera válida.")
    if not (1 <= n <= 100000000):
        raise ValidationError("La cantidad debe estar entre 1 y 100 000 000.")
    return n


def _read_nonnegative(raw):
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("Ingresa una cantidad entera válida.")
    if not (0 <= n <= 100000000):
        raise ValidationError("La cantidad debe estar entre 0 y 100 000 000.")
    return n


def _save_form(form, message):
    if not form.is_valid():
        errors = "; ".join(
            f"{key}: {', '.join(str(v) for v in errs)}"
            for key, errs in form.errors.items()
        )
        raise ValidationError(errors[:550])
    form.save()
    return message


@login_required
@require_POST
def inventory_action(request):
    action = request.POST.get("action", "")
    admin_actions = {"branch", "location", "category", "product", "edit_product", "demo", "import", "store_minimum"}
    stock_actions = {"stock", "transfer"}
    if action in admin_actions:
        if not request.user.is_superuser:
            raise PermissionDenied("Solo el administrador puede realizar esta operación.")
    elif action in stock_actions:
        if not can_move(request.user):
            raise PermissionDenied("Esta cuenta no tiene permiso para mover mercancía.")
    else:
        raise PermissionDenied("Operación no autorizada.")

    section = request.POST.get("return_to", "panel")
    if section not in SECTIONS:
        section = "panel"

    try:
        if action == "branch":
            raise ValidationError("AGROQUÍMICOS opera con un solo almacén; no se crean sucursales.")
        elif action == "location":
            selected = Branch.objects.filter(
                pk=request.POST.get("branch"), code="AGRO-ALMACEN", is_active=True
            ).first()
            if not selected:
                raise ValidationError("Selecciona el almacén AGROQUÍMICOS para crear una ubicación.")
            msg = _save_form(LocationForm(request.POST), "Estante agregado al almacén.")
        elif action == "category":
            msg = _save_form(CategoryForm(request.POST), "Categoría creada.")
        elif action == "product":
            msg = _save_form(ProductForm(request.POST), "Producto creado. Registra una entrada para cargar existencias.")
        elif action == "edit_product":
            product = get_object_or_404(Product, pk=_get_id(request.POST.get("product_id")))
            msg = _save_form(ProductForm(request.POST, instance=product), "Producto actualizado.")
        elif action == "store_minimum":
            product = get_object_or_404(Product, pk=_get_id(request.POST.get("product_id")))
            store = get_object_or_404(
                Branch, pk=_get_id(request.POST.get("branch_id")), is_active=True
            )
            raw_minimum = request.POST.get("minimum", "").strip()
            if not raw_minimum:
                BranchStockMinimum.objects.filter(product=product, branch=store).delete()
                msg = "Mínimo personalizado eliminado; se aplicará el mínimo general del producto."
            else:
                minimum = _read_nonnegative(raw_minimum)
                BranchStockMinimum.objects.update_or_create(
                    product=product, branch=store,
                    defaults={"minimum": minimum, "updated_by": request.user},
                )
                msg = f"Mínimo de {product.sku} en {store.name} actualizado a {minimum}."
        elif action == "demo":
            n, m = load_demo(actor=request.user)
            msg = f"Datos ficticios cargados: {n} productos nuevos, {m} movimientos registrados."
        elif action == "import":
            file = request.FILES.get("archivo")
            if file is None:
                raise ValidationError("Selecciona primero un archivo Excel .xlsx.")
            rows, new, changes = import_excel(upload=file, actor=request.user)
            msg = f"Excel procesado: {rows} filas, {new} productos nuevos, {changes} ajustes de existencias."
        elif action == "stock":
            product = get_object_or_404(Product, pk=_get_id(request.POST.get("product_id")), is_active=True)
            location = get_object_or_404(
                StorageLocation.objects.select_related("branch"),
                pk=_get_id(request.POST.get("location_id")), is_active=True, branch__is_active=True
            )
            kind = request.POST.get("kind")
            if kind not in {StockMovement.ENTRY, StockMovement.EXIT, StockMovement.ADJUST}:
                raise ValidationError("Tipo de movimiento no reconocido.")
            note = request.POST.get("note", "").strip()
            if kind in {StockMovement.EXIT, StockMovement.ADJUST} and not note:
                raise ValidationError("Describe el motivo de la salida o del ajuste.")
            if kind == StockMovement.ADJUST:
                desired = _read_nonnegative(request.POST.get("quantity"))
                with transaction.atomic():
                    balance, _ = StockBalance.objects.select_for_update().get_or_create(
                        product=product, location=location, defaults={"quantity": 0}
                    )
                    delta = desired - balance.quantity
                    apply_stock(
                        product=product, location=location, delta=delta,
                        actor=request.user, kind=kind, note=note
                    )
            else:
                quantity = _read_positive(request.POST.get("quantity"))
                delta = quantity if kind == StockMovement.ENTRY else -quantity
                apply_stock(
                    product=product, location=location, delta=delta,
                    actor=request.user, kind=kind, note=note
                )
            msg = "Existencias actualizadas; movimiento registrado en el historial."
        elif action == "transfer":
            product = get_object_or_404(Product, pk=_get_id(request.POST.get("product_id")), is_active=True)
            origin = get_object_or_404(StorageLocation, pk=_get_id(request.POST.get("origin_id")), is_active=True, branch__is_active=True)
            destination = get_object_or_404(StorageLocation, pk=_get_id(request.POST.get("destination_id")), is_active=True, branch__is_active=True)
            n = _read_positive(request.POST.get("quantity"))
            ref = transfer_stock(
                product=product, origin=origin, destination=destination,
                quantity=n, actor=request.user, note=request.POST.get("note", "").strip()
            )
            msg = f"Traslado registrado correctamente. Referencia {ref}."
        messages.success(request, msg)
    except ValidationError as error:
        messages.error(request, "; ".join(str(item) for item in error.messages))
    return redirect(page_url(section))


@login_required
def download_template(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Solo administradores pueden descargar la plantilla.")
    response = HttpResponse(
        excel_template(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="plantilla_inventario.xlsx"'
    return response
