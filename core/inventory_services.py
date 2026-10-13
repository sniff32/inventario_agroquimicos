"""Operaciones de inventario: nunca editar cantidades sin movimiento."""
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import StockBalance, StockMovement


@transaction.atomic
def apply_stock(*, product, location, delta, actor, kind, note="", reference="", allow_zero=False):
    """Modifica stock bloqueando la fila y conserva el antes y después."""
    delta = int(delta)
    if delta == 0 and not allow_zero:
        raise ValidationError("La cantidad no cambia; no se registró ningún movimiento.")
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        product=product, location=location, defaults={"quantity": 0}
    )
    before = balance.quantity
    after = before + delta
    if after < 0:
        raise ValidationError(
            f"Existencias insuficientes: disponibles {before}, solicitadas {abs(delta)}."
        )
    balance.quantity = after
    balance.save(update_fields=["quantity", "updated_at"])
    return StockMovement.objects.create(
        product=product, location=location, actor=actor, kind=kind,
        delta=delta, before=before, after=after,
        note=note[:255], reference=reference[:80],
    )


@transaction.atomic
def transfer_stock(*, product, origin, destination, quantity, actor, note=""):
    quantity = int(quantity)
    if quantity <= 0:
        raise ValidationError("El traslado debe ser mayor a cero.")
    if origin.pk == destination.pk:
        raise ValidationError("El origen y el destino deben ser diferentes.")
    ref = f"TR-{uuid4().hex[:12].upper()}"
    # Bloqueo de ambas filas en orden estable para reducir riesgos de deadlocks.
    for location in (origin, destination):
        StockBalance.objects.get_or_create(
            product=product, location=location, defaults={"quantity": 0}
        )
    balances = list(
        StockBalance.objects.select_for_update()
        .filter(product=product, location__in=[origin, destination]).order_by("pk")
    )
    by_location = {b.location_id: b for b in balances}
    source = by_location[origin.pk]
    target = by_location[destination.pk]
    if source.quantity < quantity:
        raise ValidationError(
            f"Existencias insuficientes en origen: disponibles {source.quantity}."
        )
    source_before = source.quantity
    target_before = target.quantity
    source.quantity -= quantity
    target.quantity += quantity
    source.save(update_fields=["quantity", "updated_at"])
    target.save(update_fields=["quantity", "updated_at"])
    StockMovement.objects.create(
        product=product, location=origin, actor=actor,
        kind=StockMovement.TRANSFER_OUT, delta=-quantity,
        before=source_before, after=source.quantity,
        note=note[:255], reference=ref,
    )
    StockMovement.objects.create(
        product=product, location=destination, actor=actor,
        kind=StockMovement.TRANSFER_IN, delta=quantity,
        before=target_before, after=target.quantity,
        note=note[:255], reference=ref,
    )
    return ref
