import pytest

from capuccino_vainilla.seeder.readonly import ReadOnlyOdoo, ReadOnlyViolation


class _Spy:
    def __init__(self):
        self.calls = []

    def search_count(self, model, domain):
        self.calls.append(("search_count", model))
        return 0

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None):
        self.calls.append(("search_read", model))
        return [{"id": 1}]

    def read(self, model, ids, fields):
        self.calls.append(("read", model))
        return [{"id": ids[0]}]

    def create(self, model, values):
        self.calls.append(("create", model))
        return 99

    def write(self, model, ids, values):
        self.calls.append(("write", model))
        return True


def test_read_methods_delegate():
    spy = _Spy()
    ro = ReadOnlyOdoo(spy)
    assert ro.search_read("product.template", [], ["id"]) == [{"id": 1}]
    assert ro.read("product.template", [5], ["id"]) == [{"id": 5}]
    assert ro.search_count("product.template", []) == 0
    assert ("create", "product.template") not in spy.calls


def test_create_raises_readonly_violation():
    ro = ReadOnlyOdoo(_Spy())
    with pytest.raises(ReadOnlyViolation):
        ro.create("product.template", {"name": "x"})


def test_write_raises_readonly_violation():
    ro = ReadOnlyOdoo(_Spy())
    with pytest.raises(ReadOnlyViolation):
        ro.write("product.template", [1], {"name": "x"})
