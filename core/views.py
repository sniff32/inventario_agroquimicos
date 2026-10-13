"""Páginas de la aplicación y administración integrada de usuarios."""
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import CreateAccountForm, ROLE_CHOICES
from .inventory_views import SECTIONS, inventory_context

ROLES = {value for value, _label in ROLE_CHOICES}


def health(request):
    """Comprobación mínima de que el proceso web responde."""
    return HttpResponse("OK", content_type="text/plain")


def _role_of(user):
    if user.is_superuser:
        return "Administrador"
    user_groups = {group.name for group in user.groups.all()}
    if "Empleado" in user_groups:
        return "Empleado"
    if "Invitado" in user_groups:
        return "Invitado"
    return "Sin asignar"


def _dashboard_context(section, form=None):
    context = {"active_section": section}
    if section == "administracion":
        users = get_user_model().objects.prefetch_related("groups").order_by("username")
        context.update(
            {
                "create_form": form if form is not None else CreateAccountForm(),
                "user_rows": [{"account": account, "role": _role_of(account)} for account in users],
                "role_choices": ROLE_CHOICES,
            }
        )
    return context


@login_required
def home(request):
    """Una sola aplicación; el administrador dispone de su propio apartado."""
    section = request.GET.get("seccion", "panel")
    if section in {"administracion", "finanzas"} and not request.user.is_superuser:
        raise PermissionDenied("Solo los administradores pueden gestionar usuarios.")
    if section not in SECTIONS and section != "administracion":
        section = "panel"
    if section == "finanzas":
        from .finance_services import financial_context
        context = {"active_section": "finanzas", **financial_context()}
    elif section == "ventas":
        from .inventory_views import can_move
        from .sale_views import sales_context
        if not can_move(request.user):
            raise PermissionDenied("No tienes permisos para consultar ventas.")
        context = sales_context(request)
    else:
        context = _dashboard_context(section) if section == "administracion" else inventory_context(request, section)
    from .inventory_views import can_move
    context["user_is_employee"] = can_move(request.user)
    return render(request, "dashboard.html", context)


def _return_to_admin():
    return redirect(reverse("home") + "?seccion=administracion")


def _set_role(user, role):
    """Conserva otros grupos ajenos a los roles de acceso."""
    user.groups.remove(*Group.objects.filter(name__in=ROLES))
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    user.is_superuser = (role == "Administrador")
    user.is_staff = (role == "Administrador")
    user.save(update_fields=["is_superuser", "is_staff"])


@login_required
@require_POST
def manage_users(request):
    """Solo superusuarios. Todas las mutaciones se reciben mediante POST + CSRF."""
    if not request.user.is_superuser:
        raise PermissionDenied("Acceso exclusivo para administradores.")

    action = request.POST.get("action", "")
    User = get_user_model()

    if action == "create":
        form = CreateAccountForm(request.POST)
        if not form.is_valid():
            return render(
                request, "dashboard.html",
                _dashboard_context("administracion", form),
                status=400,
            )
        with transaction.atomic():
            account = form.save(commit=False)
            account.is_active = True
            account.is_staff = False
            account.is_superuser = False
            account.save()
            _set_role(account, form.cleaned_data["role"])
        messages.success(request, "Cuenta creada correctamente.")
        return _return_to_admin()

    if action not in {"password", "role", "status"}:
        raise PermissionDenied("Operación no autorizada.")

    user_id = request.POST.get("user_id", "")
    if not user_id.isdecimal():
        raise Http404("Usuario no encontrado.")
    account = get_object_or_404(User, pk=int(user_id))

    if action == "password":
        password_form = SetPasswordForm(account, request.POST)
        if password_form.is_valid():
            password_form.save()
            if account.pk == request.user.pk:
                update_session_auth_hash(request, account)
            messages.success(request, "Contraseña actualizada correctamente.")
        else:
            for _field, errors in password_form.errors.items():
                for error in errors:
                    messages.error(request, str(error))
        return _return_to_admin()

    # No permitir que una cuenta administradora se quite acceso a sí misma.
    if account.pk == request.user.pk:
        messages.error(request, "No puedes modificar tu propio rol o estado desde aquí.")
        return _return_to_admin()

    if action == "role":
        role = request.POST.get("role", "")
        if role not in ROLES:
            messages.error(request, "El rol seleccionado no es válido.")
            return _return_to_admin()
        with transaction.atomic():
            _set_role(account, role)
        messages.success(request, "Permisos de la cuenta actualizados.")
        return _return_to_admin()

    if action == "status":
        account.is_active = not account.is_active
        account.save(update_fields=["is_active"])
        messages.success(request, "Estado de la cuenta actualizado.")
        return _return_to_admin()

    raise PermissionDenied("Operación no autorizada.")
