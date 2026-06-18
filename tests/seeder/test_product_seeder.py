from capuccino_vainilla.seeder.product_seeder import AttributeMaps, ProductSeeder
from tests.seeder.fakes import FakeOdoo


def _source_with_attributes() -> FakeOdoo:
    return FakeOdoo({
        "product.attribute": [
            {"id": 10, "name": "Color"},
            {"id": 11, "name": "Tamaño"},
        ],
        "product.attribute.value": [
            {"id": 100, "name": "Rojo", "attribute_id": [10, "Color"]},
            {"id": 101, "name": "Azul", "attribute_id": [10, "Color"]},
            {"id": 102, "name": "Grande", "attribute_id": [11, "Tamaño"]},
        ],
    })


def test_seed_attributes_creates_and_maps_ids():
    source, target = _source_with_attributes(), FakeOdoo()
    maps = ProductSeeder(source, target).seed_attributes()

    assert isinstance(maps, AttributeMaps)
    # Todos los atributos y valores fueron mapeados.
    assert set(maps.attribute_ids.keys()) == {10, 11}
    assert set(maps.value_ids.keys()) == {100, 101, 102}
    # El valor "Rojo" en destino apunta al atributo destino mapeado de "Color".
    dst_color = maps.attribute_ids[10]
    rojo = [r for r in target.tables["product.attribute.value"]
            if r["name"] == "Rojo"][0]
    assert rojo["attribute_id"] == dst_color


def test_seed_attributes_is_idempotent():
    source, target = _source_with_attributes(), FakeOdoo()
    ProductSeeder(source, target).seed_attributes()
    ProductSeeder(source, target).seed_attributes()  # segunda corrida
    # No se duplican atributos ni valores.
    assert len(target.tables["product.attribute"]) == 2
    assert len(target.tables["product.attribute.value"]) == 3


def _source_with_products() -> FakeOdoo:
    return FakeOdoo({
        "product.attribute": [{"id": 10, "name": "Color"}],
        "product.attribute.value": [
            {"id": 100, "name": "Rojo", "attribute_id": [10, "Color"]},
        ],
        "product.template": [
            {"id": 1, "name": "Remera", "default_code": "REM-001",
             "list_price": 5000.0, "description_sale": "Algodón",
             "qty_available": 7.0, "attribute_line_ids": [500],
             "optional_product_ids": []},
            {"id": 2, "name": "Sin SKU", "default_code": False,
             "list_price": 100.0, "description_sale": "",
             "qty_available": 0.0, "attribute_line_ids": [],
             "optional_product_ids": []},
        ],
        "product.template.attribute.line": [
            {"id": 500, "attribute_id": [10, "Color"], "value_ids": [100]},
        ],
    })


def test_seed_products_creates_with_sku_and_skips_without():
    source, target = _source_with_products(), FakeOdoo()
    seeder = ProductSeeder(source, target)
    maps = seeder.seed_attributes()
    tmpl_map = seeder.seed_products(maps)

    dst_products = target.tables["product.template"]
    assert len(dst_products) == 1                      # el sin SKU se omitió
    assert dst_products[0]["default_code"] == "REM-001"
    assert seeder.report.products_created == 1
    assert seeder.report.products_skipped == 1
    assert 1 in tmpl_map                               # template origen 1 mapeado
    # qty_available NO se escribe (campo calculado).
    assert "qty_available" not in dst_products[0]
    # La línea de atributo usa el value_id y attribute_id remapeados al destino.
    line_cmd = dst_products[0]["attribute_line_ids"][0]
    assert line_cmd[0] == 0  # comando (0, 0, {...})
    assert line_cmd[1] == 0
    assert line_cmd[2]["attribute_id"] == maps.attribute_ids[10]
    assert line_cmd[2]["value_ids"] == [(6, 0, [maps.value_ids[100]])]


def test_seed_products_idempotent_updates_not_duplicates():
    source, target = _source_with_products(), FakeOdoo()
    seeder = ProductSeeder(source, target)
    maps = seeder.seed_attributes()
    seeder.seed_products(maps)

    seeder2 = ProductSeeder(source, target)
    seeder2.seed_products(seeder2.seed_attributes())
    assert len(target.tables["product.template"]) == 1   # no duplica
    assert seeder2.report.products_updated == 1
    # En update NO se reenvían attribute_line_ids (evita duplicar líneas).
    update_call = [c for c in target.write_calls if c[0] == "product.template"][-1]
    assert "attribute_line_ids" not in update_call[2]


def test_seed_products_skips_attribute_line_with_all_unmapped_values():
    """Línea de atributo con todos los valores sin mapear → no se emite ningún comando."""
    # El origen tiene un atributo y una línea que referencia valores NO presentes
    # en product.attribute.value (ids 999/998 no existen en la tabla de valores).
    source = FakeOdoo({
        "product.attribute": [
            {"id": 10, "name": "Color"},
        ],
        # Sin valores de atributo en el origen: 999/998 no están en esta tabla.
        "product.attribute.value": [],
        "product.template": [
            {"id": 1, "name": "Remera", "default_code": "REM-002",
             "list_price": 3000.0, "description_sale": "",
             "qty_available": 0.0, "attribute_line_ids": [600],
             "optional_product_ids": []},
        ],
        "product.template.attribute.line": [
            # value_ids apunta a valores que nunca fueron copiados al mapa
            {"id": 600, "attribute_id": [10, "Color"], "value_ids": [999, 998]},
        ],
    })
    target = FakeOdoo()
    seeder = ProductSeeder(source, target)
    maps = seeder.seed_attributes()
    seeder.seed_products(maps)

    dst_products = target.tables["product.template"]
    # El producto se creó (tiene SKU)
    assert len(dst_products) == 1
    assert dst_products[0]["default_code"] == "REM-002"
    # Pero no se generó ninguna línea de atributo (todos los valores eran no mapeados)
    assert dst_products[0]["attribute_line_ids"] == []
