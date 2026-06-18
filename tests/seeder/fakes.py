"""Doble de Odoo en memoria para tests del seeder.

Soporta solo dominios de igualdad: [("campo", "=", valor), ...] (los únicos
que el seeder usa). create() asigna ids incrementales por modelo.
"""

from __future__ import annotations


class FakeOdoo:
    def __init__(self, seed: dict[str, list[dict]] | None = None):
        # tables[model] = lista de dicts (cada uno con "id")
        self.tables: dict[str, list[dict]] = {}
        self._next_id: dict[str, int] = {}
        self.write_calls: list[tuple] = []
        for model, rows in (seed or {}).items():
            for row in rows:
                self._insert(model, dict(row))

    def _insert(self, model: str, row: dict) -> int:
        # Determinar id sin mutar el dict original
        explicit = row.get("id")
        rid = explicit if explicit else self._alloc(model)
        # Avanzar el contador si el id explícito supera el actual
        if explicit:
            current = self._next_id.get(model, 1)
            if explicit >= current:
                self._next_id[model] = explicit + 1
        stored = {**row, "id": rid}
        self.tables.setdefault(model, []).append(stored)
        return rid

    def _alloc(self, model: str) -> int:
        nxt = self._next_id.get(model, 1)
        self._next_id[model] = nxt + 1
        return nxt

    def _matches(self, row: dict, domain: list) -> bool:
        for field, op, value in domain:
            if op != "=":
                raise NotImplementedError(f"FakeOdoo solo soporta '=', no {op!r}")
            if row.get(field) != value:
                return False
        return True

    def search_count(self, model, domain):
        return sum(1 for r in self.tables.get(model, []) if self._matches(r, domain))

    def search_read(self, model, domain, fields, offset=0, limit=None, order=None):
        rows = [r for r in self.tables.get(model, []) if self._matches(r, domain)]
        rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return [{f: r.get(f) for f in (["id"] + fields)} for r in rows]

    def read(self, model, ids, fields):
        by_id = {r["id"]: r for r in self.tables.get(model, [])}
        return [
            {f: by_id[i].get(f) for f in (["id"] + fields)}
            for i in ids if i in by_id
        ]

    def create(self, model, values):
        return self._insert(model, dict(values))

    def write(self, model, ids, values):
        self.write_calls.append((model, list(ids), dict(values)))
        ids_set = set(ids)
        # Reconstruir la lista con nuevos dicts para no mutar el estado compartido
        self.tables[model] = [
            {**r, **values} if r["id"] in ids_set else r
            for r in self.tables.get(model, [])
        ]
        return True
