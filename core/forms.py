"""Formularios seguros para que el administrador gestione cuentas."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

ROLE_CHOICES = (
    ("Empleado", "Empleado"),
    ("Invitado", "Invitado (solo consulta)"),
    ("Administrador", "Administrador"),
)


class CreateAccountForm(UserCreationForm):
    email = forms.EmailField(label="Correo electrónico", required=True)
    role = forms.ChoiceField(label="Tipo de cuenta", choices=ROLE_CHOICES)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario"
        self.fields["first_name"].label = "Nombre"
        self.fields["last_name"].label = "Apellidos"
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmar contraseña"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este correo ya está registrado.")
        return email


from .models import Branch, Category, Product, StorageLocation


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ("code", "name", "address")
        labels = {"code": "Clave", "name": "Nombre", "address": "Dirección / referencia"}


class LocationForm(forms.ModelForm):
    class Meta:
        model = StorageLocation
        fields = ("branch", "code", "description")
        labels = {"branch": "Sucursal", "code": "Repisa / ubicación", "description": "Descripción"}


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name",)
        labels = {"name": "Nombre de categoría"}


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ("sku", "name", "category", "brand", "unit", "price", "wholesale_price", "wholesale_min_qty", "cost", "min_stock", "description")
        labels = {
            "sku": "Código / SKU", "name": "Nombre", "category": "Categoría",
            "brand": "Marca", "unit": "Unidad", "price": "Precio de venta",
            "wholesale_price": "Precio por mayoreo", "wholesale_min_qty": "Cantidad mínima por mayoreo",
            "cost": "Costo", "min_stock": "Existencia mínima", "description": "Descripción",
        }
