"""Rutas iniciales del proyecto."""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core.views import health, home, manage_users
from core.inventory_views import download_template, inventory_action
from core.sale_views import sale_action, sale_docx
from core.sale_lookup import search_sale_products, sale_product_detail
from core.finance_views import finance_action

urlpatterns = [
    path("", home, name="home"),
    path("salud/", health, name="health"),
    path("ventas/accion/", sale_action, name="sale_action"),
    path("finanzas/accion/", finance_action, name="finance_action"),
    path("ventas/buscar/", search_sale_products, name="sale_search"),
    path("ventas/producto/<int:balance_id>/", sale_product_detail, name="sale_product_detail"),
    path("ventas/<int:sale_id>/orden.docx", sale_docx, name="sale_docx"),
    path("inventario/accion/", inventory_action, name="inventory_action"),
    path("inventario/plantilla/", download_template, name="inventory_template"),
    path("cuentas/gestionar/", manage_users, name="manage_users"),
    path("admin/", admin.site.urls),
    path(
        "cuentas/ingresar/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("cuentas/salir/", auth_views.LogoutView.as_view(), name="logout"),
]

admin.site.site_header = "FERMO · Inventarios y ventas"
admin.site.site_title = "Administración FERMO"
admin.site.index_title = "Administración del sistema"
