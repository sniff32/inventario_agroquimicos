"""Modelos persistentes de catálogo, sucursales, existencias y auditoría."""
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Branch(models.Model):
    code = models.CharField("Clave de sucursal", max_length=24, unique=True)
    name = models.CharField("Nombre", max_length=120)
    address = models.CharField("Dirección o referencia", max_length=255, blank=True)
    is_demo = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Sucursal"
        verbose_name_plural = "Sucursales"

    def __str__(self):
        return self.name


class StorageLocation(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="locations")
    code = models.CharField("Ubicación", max_length=70)
    description = models.CharField(max_length=160, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("branch__name", "code")
        constraints = [models.UniqueConstraint(fields=["branch", "code"], name="uniq_location_in_branch")]

    def __str__(self):
        return f"{self.branch.name} / {self.code}"


class Category(models.Model):
    name = models.CharField(max_length=90, unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "Categorías"

    def __str__(self):
        return self.name


class Product(models.Model):
    sku = models.CharField("Código de producto", max_length=64, unique=True)
    name = models.CharField("Producto", max_length=180)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT)
    brand = models.CharField(max_length=100, blank=True)
    unit = models.CharField("Unidad de medida", max_length=30, default="pieza")
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    min_stock = models.PositiveIntegerField(default=5)
    wholesale_price = models.DecimalField("Precio mayoreo", max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    wholesale_min_qty = models.PositiveIntegerField("Unidades mínimas mayoreo", default=10, validators=[MinValueValidator(1)])
    is_demo = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return f"{self.sku} · {self.name}"


class StockBalance(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="balances")
    location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="balances")
    quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "location"], name="uniq_product_location")]


class StockMovement(models.Model):
    ENTRY = "ENTRADA"
    EXIT = "SALIDA"
    ADJUST = "AJUSTE"
    IMPORT = "IMPORTACION"
    DEMO = "DEMO"
    TRANSFER_IN = "TRASLADO_ENTRADA"
    TRANSFER_OUT = "TRASLADO_SALIDA"
    TYPES = [
        (ENTRY, "Entrada"), (EXIT, "Salida"), (ADJUST, "Ajuste"),
        (IMPORT, "Importación Excel"), (DEMO, "Carga de demostración"),
        (TRANSFER_IN, "Traslado recibido"), (TRANSFER_OUT, "Traslado enviado"),
    ]

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="movements")
    location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="movements")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements")
    kind = models.CharField(max_length=20, choices=TYPES)
    delta = models.IntegerField(help_text="Variación firmada de unidades")
    before = models.PositiveIntegerField()
    after = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=["-created_at"], name="movement_when_idx"),
            models.Index(fields=["product", "-created_at"], name="movement_product_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.product.sku}: {self.delta:+d}"


class BranchStockMinimum(models.Model):
    """Mínimo específico por producto y sucursal. Si no existe, aplica Product.min_stock."""
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="branch_minimums")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="stock_minimums")
    minimum = models.PositiveIntegerField("Mínimo en esta sucursal")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "branch"], name="uniq_product_minimum_per_branch"
            )
        ]
        verbose_name = "Mínimo por sucursal"
        verbose_name_plural = "Mínimos por sucursal"


class SaleSequence(models.Model):
    """Folio continuo de operaciones confirmadas con bloqueo en PostgreSQL."""
    name = models.CharField(max_length=20, primary_key=True, default="AGROQUIMICOS")
    last_number = models.PositiveIntegerField(default=0)


class Sale(models.Model):
    RETAIL = "MENUDEO"
    WHOLESALE = "MAYOREO"
    MIXED = "MIXTA"
    TYPES = [(RETAIL, "Menudeo"), (WHOLESALE, "Mayoreo"), (MIXED, "Mixta")]

    number = models.CharField("Folio", max_length=24, unique=True)
    sale_type = models.CharField("Tipo de venta", max_length=12, choices=TYPES)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="sales")
    customer_name = models.CharField("Cliente", max_length=180)
    customer = models.ForeignKey("Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="sales")
    payment_term = models.CharField(max_length=16, choices=[("SIN_CLASIFICAR", "Sin clasificar"), ("CONTADO", "Contado"), ("CREDITO", "Crédito")], default="SIN_CLASIFICAR")
    due_date = models.DateField(null=True, blank=True)
    customer_contact = models.CharField("Contacto", max_length=120, blank=True)
    delivery_date = models.DateField("Fecha de salida / entrega")
    note = models.CharField("Observaciones", max_length=255, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    gross_subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="MXN")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [models.Index(fields=["-created_at"], name="sale_created_idx")]

    def __str__(self):
        return f"{self.number} · {self.customer_name}"


class SaleItem(models.Model):
    sale_type = models.CharField(
        "Modalidad del artículo", max_length=12,
        choices=[(Sale.RETAIL, "Menudeo"), (Sale.WHOLESALE, "Mayoreo")],
        default=Sale.RETAIL,
    )
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_items")
    location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT, related_name="sale_items")
    sku_snapshot = models.CharField(max_length=64)
    name_snapshot = models.CharField(max_length=180)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    base_unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.PositiveSmallIntegerField(default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ("id",)


class Supplier(models.Model):
    name = models.CharField("Proveedor", max_length=180, unique=True)
    contact = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    note = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Customer(models.Model):
    name = models.CharField("Cliente o productor", max_length=180, unique=True)
    contact = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Purchase(models.Model):
    CASH = "CONTADO"
    CREDIT = "CREDITO"
    TERMS = [(CASH, "Contado"), (CREDIT, "Crédito")]
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchases")
    location = models.ForeignKey(StorageLocation, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total = models.DecimalField(max_digits=14, decimal_places=2)
    term = models.CharField(max_length=10, choices=TERMS)
    due_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")


class PurchasePayment(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    reference = models.CharField(max_length=80, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")


class SalePayment(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    reference = models.CharField(max_length=80, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "pk")
