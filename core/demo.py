"""50 productos ficticios de una distribuidora de productos agrícolas.

Carga explícita por administrador: no elimina saldos ni historiales antiguos.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction

from .inventory_services import apply_stock
from .models import Branch, Category, Product, StockMovement, StorageLocation

# Artículo, categoría, marca, unidad, costo unitario, menudeo, unidades iniciales.
# Precios exclusivamente demostrativos, no cotizaciones del mercado.
DEMO_PRODUCTS = [
    ("Fertilizante NPK 17-17-17 25 kg", "Fertilizantes", "Genérico demo", "saco", 410, 555, 35),
    ("Urea granulada 46-0-0 50 kg", "Fertilizantes", "Genérico demo", "saco", 540, 725, 28),
    ("Sulfato de amonio 50 kg", "Fertilizantes", "Genérico demo", "saco", 380, 505, 42),
    ("Fosfato diamónico DAP 50 kg", "Fertilizantes", "Genérico demo", "saco", 810, 1040, 20),
    ("Nitrato de calcio 25 kg", "Fertilizantes", "Genérico demo", "saco", 485, 650, 24),
    ("Nitrato de potasio 25 kg", "Fertilizantes", "Genérico demo", "saco", 690, 890, 16),
    ("Sulfato de potasio 25 kg", "Fertilizantes", "Genérico demo", "saco", 580, 760, 18),
    ("Sulfato de magnesio 25 kg", "Fertilizantes", "Genérico demo", "saco", 230, 340, 36),
    ("Fertilizante foliar balanceado 1 L", "Fertilizantes foliares", "Genérico demo", "botella", 105, 165, 61),
    ("Fertilizante foliar alto fósforo 1 L", "Fertilizantes foliares", "Genérico demo", "botella", 112, 175, 44),
    ("Fertilizante foliar alto potasio 1 L", "Fertilizantes foliares", "Genérico demo", "botella", 128, 195, 42),
    ("Quelato de hierro 1 kg", "Micronutrientes", "Genérico demo", "bolsa", 255, 355, 23),
    ("Micronutrientes mezcla 1 kg", "Micronutrientes", "Genérico demo", "bolsa", 180, 275, 27),
    ("Calcio boro líquido 1 L", "Micronutrientes", "Genérico demo", "botella", 140, 220, 32),
    ("Ácido húmico líquido 1 L", "Bioestimulantes", "Genérico demo", "botella", 115, 185, 38),
    ("Extracto de algas 1 L", "Bioestimulantes", "Genérico demo", "botella", 160, 245, 20),
    ("Enraizador vegetal 1 L", "Bioestimulantes", "Genérico demo", "botella", 175, 270, 19),
    ("Aminoácidos agrícolas 1 L", "Bioestimulantes", "Genérico demo", "botella", 150, 235, 37),
    ("Glifosato formulado 1 L - demostración", "Herbicidas", "Genérico demo", "botella", 115, 185, 29),
    ("Herbicida selectivo hoja ancha 1 L", "Herbicidas", "Genérico demo", "botella", 155, 240, 22),
    ("Herbicida preemergente 1 L", "Herbicidas", "Genérico demo", "botella", 210, 325, 18),
    ("Herbicida de contacto 1 L", "Herbicidas", "Genérico demo", "botella", 195, 305, 15),
    ("Coadyuvante agrícola 1 L", "Coadyuvantes", "Genérico demo", "botella", 90, 145, 65),
    ("Adherente dispersante 1 L", "Coadyuvantes", "Genérico demo", "botella", 85, 135, 46),
    ("Aceite mineral agrícola 1 L", "Coadyuvantes", "Genérico demo", "botella", 110, 175, 51),
    ("Jabón potásico agrícola 1 L", "Control biológico", "Genérico demo", "botella", 105, 165, 34),
    ("Extracto botánico para plagas 1 L", "Control biológico", "Genérico demo", "botella", 185, 280, 25),
    ("Bioinsecticida Bacillus 500 g", "Control biológico", "Genérico demo", "frasco", 210, 325, 18),
    ("Trampa adhesiva amarilla 10 piezas", "Monitoreo de plagas", "Genérico demo", "paquete", 65, 110, 70),
    ("Trampa adhesiva azul 10 piezas", "Monitoreo de plagas", "Genérico demo", "paquete", 65, 110, 48),
    ("Insecticida agrícola concentrado 250 ml", "Insecticidas", "Genérico demo", "frasco", 130, 215, 32),
    ("Insecticida agrícola concentrado 1 L", "Insecticidas", "Genérico demo", "botella", 340, 495, 20),
    ("Insecticida sistémico 250 ml", "Insecticidas", "Genérico demo", "frasco", 205, 310, 22),
    ("Acaricida agrícola 250 ml", "Insecticidas", "Genérico demo", "frasco", 195, 295, 19),
    ("Fungicida cúprico 1 kg", "Fungicidas", "Genérico demo", "bolsa", 180, 275, 42),
    ("Fungicida azufrado 1 kg", "Fungicidas", "Genérico demo", "bolsa", 95, 155, 65),
    ("Fungicida sistémico 250 ml", "Fungicidas", "Genérico demo", "frasco", 225, 355, 16),
    ("Fungicida preventivo 1 kg", "Fungicidas", "Genérico demo", "bolsa", 170, 260, 29),
    ("Tratamiento para semillas 250 ml", "Tratamiento de semillas", "Genérico demo", "frasco", 170, 255, 24),
    ("Semilla de maíz 1 kg", "Semillas", "Genérico demo", "bolsa", 135, 215, 41),
    ("Semilla de frijol 1 kg", "Semillas", "Genérico demo", "bolsa", 85, 140, 34),
    ("Semilla de cilantro 250 g", "Semillas", "Genérico demo", "bolsa", 90, 150, 39),
    ("Semilla de alfalfa 1 kg", "Semillas", "Genérico demo", "bolsa", 220, 335, 18),
    ("Semilla de jitomate 100 g", "Semillas", "Genérico demo", "sobre", 180, 275, 20),
    ("Sustrato universal 20 L", "Sustratos", "Genérico demo", "bolsa", 92, 150, 48),
    ("Turba agrícola 50 L", "Sustratos", "Genérico demo", "saco", 255, 365, 22),
    ("Perlita hortícola 10 L", "Sustratos", "Genérico demo", "bolsa", 80, 130, 37),
    ("Guantes nitrilo para campo par", "Equipo de protección", "Genérico demo", "par", 30, 55, 75),
    ("Gafas de seguridad agrícola", "Equipo de protección", "Genérico demo", "pieza", 45, 85, 28),
    ("Aspersor manual 5 L", "Equipos agrícolas", "Genérico demo", "pieza", 235, 360, 13),
]
assert len(DEMO_PRODUCTS) == 50

WAREHOUSE_CODE = "AGRO-ALMACEN"
RACKS = ("Pasillo A · Estante 1", "Pasillo A · Estante 2", "Pasillo B · Estante 1",
         "Pasillo B · Estante 2", "Zona de cajas")


@transaction.atomic
def load_demo(*, actor):
    """Retira del catálogo las demos viejas y da de alta 50 productos agrícolas sin destruir auditoría.

    Nunca se alteran artículos reales ni cantidades de prueba ya editadas.
    No se duplica la carga inicial al repetir el proceso.
    """
    Product.objects.filter(is_demo=True).exclude(sku__startswith="AGR-").update(is_active=False)
    Branch.objects.filter(is_demo=True).exclude(code=WAREHOUSE_CODE).update(is_active=False)
    branch, _ = Branch.objects.get_or_create(
        code=WAREHOUSE_CODE,
        defaults={"name":"Almacén principal", "is_demo":True},
    )
    if not branch.is_active:
        branch.is_active = True
        branch.save(update_fields=["is_active"])
    locations = []
    for code in RACKS:
        loc, _ = StorageLocation.objects.get_or_create(branch=branch, code=code)
        locations.append(loc)
    created_count, movements = 0, 0
    for i, (name, cat, brand, unit, cost, price, qty) in enumerate(DEMO_PRODUCTS, 1):
        category, _ = Category.objects.get_or_create(name=cat)
        sku = f"AGR-{i:03d}"
        product, created = Product.objects.get_or_create(
            sku=sku,
            defaults={
                "name": name, "category":category, "brand":brand, "unit":unit,
                "cost":Decimal(cost), "price":Decimal(price),
                "wholesale_price": (Decimal(price) * Decimal("0.92")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP),
                "wholesale_min_qty":10, "min_stock":15, "is_demo":True,
            },
        )
        created_count += int(created)
        if not product.is_demo:
            continue
        if not product.is_active:
            product.is_active = True
            product.save(update_fields=["is_active"])
        location = locations[(i - 1) % len(locations)]
        if StockMovement.objects.filter(product=product, kind=StockMovement.DEMO,
                                        reference="AGRO-DEMO").exists():
            continue
        apply_stock(
            product=product, location=location, delta=qty, actor=actor,
            kind=StockMovement.DEMO,
            note="Existencia ficticia inicial de productos agrícolas para simulación",
            reference="AGRO-DEMO",
        )
        movements += 1
    return created_count, movements
