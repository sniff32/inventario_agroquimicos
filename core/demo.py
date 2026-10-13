"""50 productos ficticios de una distribuidora de abarrotes.

Carga explícita por administrador: no elimina saldos ni historiales antiguos.
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction

from .inventory_services import apply_stock
from .models import Branch, Category, Product, StockMovement, StorageLocation

# Artículo, categoría, marca, unidad, costo unitario, menudeo, unidades iniciales.
# Precios exclusivamente demostrativos, no cotizaciones del mercado.
DEMO_PRODUCTS = [
    ("Arroz blanco 1 kg","Granos y cereales","Campo Claro","bolsa",19,27,110),
    ("Frijol negro 1 kg","Granos y cereales","La Cosecha","bolsa",24,35,85),
    ("Lenteja 500 g","Granos y cereales","La Cosecha","bolsa",13,20,52),
    ("Avena en hojuelas 400 g","Granos y cereales","Buen Día","bolsa",15,24,68),
    ("Azúcar estándar 1 kg","Despensa básica","Dulce Hogar","bolsa",19,29,95),
    ("Sal refinada 1 kg","Despensa básica","Mesa Fina","bolsa",9,15,135),
    ("Harina de trigo 1 kg","Despensa básica","Molino Norte","bolsa",17,26,47),
    ("Aceite vegetal 900 ml","Aceites y aderezos","Sol Dorado","botella",30,44,75),
    ("Aceite de oliva 250 ml","Aceites y aderezos","Oliva Real","botella",55,79,18),
    ("Mayonesa 390 g","Aceites y aderezos","Buen Sabor","frasco",27,39,40),
    ("Catsup 370 g","Aceites y aderezos","Buen Sabor","botella",20,32,58),
    ("Salsa picante 150 ml","Aceites y aderezos","Fuego","botella",10,17,81),
    ("Atún en agua 140 g","Enlatados","Costa Azul","lata",17,26,92),
    ("Sardina en tomate 425 g","Enlatados","Marina","lata",25,38,34),
    ("Elote en lata 220 g","Enlatados","La Huerta","lata",15,24,49),
    ("Chícharos en lata 220 g","Enlatados","La Huerta","lata",14,22,29),
    ("Leche evaporada 360 g","Lácteos envasados","Vaquita","lata",19,30,61),
    ("Leche condensada 387 g","Lácteos envasados","Dulce Leche","lata",22,34,55),
    ("Leche UHT entera 1 L","Lácteos envasados","Pradera","caja",18,28,120),
    ("Leche deslactosada 1 L","Lácteos envasados","Pradera","caja",21,32,44),
    ("Café soluble 100 g","Café y bebidas calientes","Café Monte","frasco",57,82,28),
    ("Café molido 250 g","Café y bebidas calientes","Café Monte","bolsa",52,75,25),
    ("Chocolate en polvo 400 g","Café y bebidas calientes","Chocolinda","bolsa",31,47,43),
    ("Té de manzanilla 20 sobres","Café y bebidas calientes","Valle Verde","caja",17,27,13),
    ("Galletas marías 170 g","Galletas y pan","Dulce Tarde","paquete",13,21,104),
    ("Galletas de chocolate 120 g","Galletas y pan","Dulce Tarde","paquete",12,20,67),
    ("Pan tostado 210 g","Galletas y pan","Horno Feliz","paquete",21,32,30),
    ("Pan dulce empaquetado 2 pzas","Galletas y pan","Horno Feliz","paquete",14,24,46),
    ("Pasta espagueti 200 g","Pastas y sopas","Molino Norte","bolsa",8,14,114),
    ("Pasta codito 200 g","Pastas y sopas","Molino Norte","bolsa",8,14,89),
    ("Sopa instantánea vaso 64 g","Pastas y sopas","Sopa Lista","vaso",9,16,140),
    ("Consomé de pollo 100 g","Pastas y sopas","Buen Sabor","frasco",15,25,60),
    ("Agua natural 600 ml","Bebidas","Agua Clara","botella",6,12,225),
    ("Agua natural 1.5 L","Bebidas","Agua Clara","botella",11,20,160),
    ("Refresco cola 600 ml","Bebidas","Burbuja","botella",12,21,215),
    ("Refresco naranja 600 ml","Bebidas","Burbuja","botella",12,20,74),
    ("Jugo de manzana 1 L","Bebidas","Frutal","caja",18,30,55),
    ("Bebida deportiva 600 ml","Bebidas","Vital","botella",15,25,39),
    ("Papas fritas sal 45 g","Botanas y dulces","Crocante","bolsa",11,19,132),
    ("Cacahuates salados 100 g","Botanas y dulces","Botana Mix","bolsa",13,22,72),
    ("Paleta de caramelo 20 pzas","Botanas y dulces","Dulcelandia","bolsa",24,38,33),
    ("Chocolate en barra 40 g","Botanas y dulces","Chocolinda","pieza",11,20,105),
    ("Detergente en polvo 1 kg","Limpieza del hogar","Brillo","bolsa",32,49,44),
    ("Cloro líquido 1 L","Limpieza del hogar","LimpiaMax","botella",12,21,80),
    ("Suavizante 850 ml","Limpieza del hogar","Suavecito","botella",22,36,27),
    ("Lavatrastes 750 ml","Limpieza del hogar","LimpiaMax","botella",17,29,62),
    ("Papel higiénico 4 rollos","Higiene y papel","Nube","paquete",24,39,95),
    ("Servilletas 250 pzas","Higiene y papel","Nube","paquete",17,28,12),
    ("Pasta dental 100 ml","Higiene personal","Sonrisa","tubo",21,35,35),
    ("Jabón de tocador 150 g","Higiene personal","Fresco","pieza",11,19,8),
]
assert len(DEMO_PRODUCTS) == 50

WAREHOUSE_CODE = "FERMO-ALMACEN"
RACKS = ("Pasillo A · Estante 1", "Pasillo A · Estante 2", "Pasillo B · Estante 1",
         "Pasillo B · Estante 2", "Zona de cajas")


@transaction.atomic
def load_demo(*, actor):
    """Retira del catálogo las demos viejas y da de alta 50 abarrotes sin destruir auditoría.

    Nunca se alteran artículos reales ni cantidades de prueba ya editadas.
    No se duplica la carga inicial al repetir el proceso.
    """
    Product.objects.filter(is_demo=True).exclude(sku__startswith="ABR-").update(is_active=False)
    Branch.objects.filter(is_demo=True).exclude(code=WAREHOUSE_CODE).update(is_active=False)
    branch, _ = Branch.objects.get_or_create(
        code=WAREHOUSE_CODE,
        defaults={"name":"Almacén FERMO", "is_demo":True},
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
        sku = f"ABR-{i:03d}"
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
                                        reference="ABARROTES-DEMO").exists():
            continue
        apply_stock(
            product=product, location=location, delta=qty, actor=actor,
            kind=StockMovement.DEMO,
            note="Existencia ficticia inicial de abarrotes para simulación",
            reference="ABARROTES-DEMO",
        )
        movements += 1
    return created_count, movements
