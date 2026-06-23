#!/usr/bin/env python
"""Helper de bootstrap para el Odoo LOCAL de pruebas (vía XML-RPC).

Lo usa `scripts/setup-test.ps1`. Tres operaciones, todas idempotentes:

  wait            espera a que el servidor Odoo acepte conexiones
  create-db       crea la base + usuario admin (no-op si ya existe)
  install-module  instala un módulo, ej. `stock` (no-op si ya está instalado)

Sólo usa la librería estándar (`xmlrpc.client`), así que no agrega dependencias.

⚠️  Pensado EXCLUSIVAMENTE para instancias locales de prueba. No apuntar a
    producción: crea bases y usa el master password del database manager.
"""

from __future__ import annotations

import argparse
import sys
import time
import xmlrpc.client


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _is_local(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url or "host.docker.internal" in url


def _proxy(url: str, path: str) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/{path}", allow_none=True)


def cmd_wait(args: argparse.Namespace) -> int:
    """Bloquea hasta que el servidor Odoo responde, o hasta el timeout."""
    deadline = time.monotonic() + args.timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            version = _proxy(args.url, "common").version()
            print(f"Odoo OK — server {version.get('server_version', '?')}")
            return 0
        except Exception as exc:  # noqa: BLE001 — el wait tolera cualquier fallo transitorio
            last_err = exc
            time.sleep(args.interval)
    _eprint(f"Timeout esperando a Odoo en {args.url} ({args.timeout}s). Último error: {last_err}")
    return 1


def cmd_create_db(args: argparse.Namespace) -> int:
    """Crea la base + admin. No-op si ya existe."""
    if not _is_local(args.url):
        _eprint(f"NEGADO: {args.url} no parece local. Este helper es solo para pruebas.")
        return 2
    db = _proxy(args.url, "db")
    try:
        existing = db.list()
    except Exception as exc:  # noqa: BLE001
        _eprint(f"No se pudo listar las bases de Odoo: {exc}")
        return 1

    if args.db_name in existing:
        print(f"La base '{args.db_name}' ya existe — se omite la creación.")
        return 0

    print(f"Creando la base '{args.db_name}' (puede tardar ~30-60s)...")
    try:
        db.create_database(
            args.master_pwd,   # master password del database manager
            args.db_name,
            args.demo,         # cargar datos de demostración
            args.lang,
            args.admin_password,
            args.admin_login,
            args.country_code or None,
        )
    except xmlrpc.client.Fault as fault:
        _eprint(f"Odoo rechazó la creación: {fault.faultString.strip()}")
        if "Access Denied" in fault.faultString or "password" in fault.faultString.lower():
            _eprint("→ Revisá el MASTER PASSWORD del database manager (parámetro --master-pwd).")
        return 1
    except Exception as exc:  # noqa: BLE001
        _eprint(f"Error creando la base: {exc}")
        return 1

    print(f"Base '{args.db_name}' creada con admin '{args.admin_login}'.")
    return 0


def cmd_install_module(args: argparse.Namespace) -> int:
    """Instala un módulo por nombre técnico. No-op si ya está instalado."""
    try:
        uid = _proxy(args.url, "common").authenticate(
            args.db_name, args.admin_login, args.admin_password, {}
        )
    except Exception as exc:  # noqa: BLE001
        _eprint(f"No se pudo autenticar contra '{args.db_name}': {exc}")
        return 1
    if not uid:
        _eprint("Autenticación rechazada: revisá usuario/contraseña del admin de Odoo.")
        return 1

    models = _proxy(args.url, "object")

    def execute(model: str, method: str, *params: object) -> object:
        return models.execute_kw(args.db_name, uid, args.admin_password, model, method, list(params))

    ids = execute("ir.module.module", "search", [["name", "=", args.module]])
    if not ids:
        _eprint(f"No existe el módulo '{args.module}' en este Odoo.")
        return 1

    state = execute("ir.module.module", "read", ids, ["state"])  # type: ignore[arg-type]
    current = state[0]["state"] if state else "unknown"  # type: ignore[index]
    if current == "installed":
        print(f"El módulo '{args.module}' ya está instalado — se omite.")
        return 0

    print(f"Instalando el módulo '{args.module}' (estado actual: {current})...")
    try:
        execute("ir.module.module", "button_immediate_install", ids)
    except Exception as exc:  # noqa: BLE001
        _eprint(f"Error instalando '{args.module}': {exc}")
        return 1
    print(f"Módulo '{args.module}' instalado.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap del Odoo local de pruebas (XML-RPC).")
    parser.add_argument("--url", default="http://localhost:8069", help="URL del Odoo local.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_wait = sub.add_parser("wait", help="Espera a que Odoo responda.")
    p_wait.add_argument("--timeout", type=int, default=180)
    p_wait.add_argument("--interval", type=int, default=3)
    p_wait.set_defaults(func=cmd_wait)

    p_db = sub.add_parser("create-db", help="Crea la base + admin (idempotente).")
    p_db.add_argument("--db-name", required=True)
    p_db.add_argument("--admin-login", required=True)
    p_db.add_argument("--admin-password", required=True)
    p_db.add_argument("--master-pwd", default="admin", help="Master password del database manager.")
    p_db.add_argument("--lang", default="en_US")
    p_db.add_argument("--country-code", default="")
    p_db.add_argument("--demo", action="store_true", help="Cargar datos de demostración.")
    p_db.set_defaults(func=cmd_create_db)

    p_mod = sub.add_parser("install-module", help="Instala un módulo (idempotente).")
    p_mod.add_argument("--db-name", required=True)
    p_mod.add_argument("--admin-login", required=True)
    p_mod.add_argument("--admin-password", required=True)
    p_mod.add_argument("--module", default="stock")
    p_mod.set_defaults(func=cmd_install_module)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
