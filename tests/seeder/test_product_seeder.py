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
