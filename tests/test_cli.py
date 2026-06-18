from capuccino_vainilla.cli import main
from capuccino_vainilla.config import (
    AppConfig,
    ConfigError,
    OdooConfig,
    RuntimeConfig,
    WatcherConfig,
    WebhookConfig,
    WooConfig,
)


def _fake_config() -> AppConfig:
    """AppConfig con valores reconocibles para los tests del banner."""
    return AppConfig(
        odoo=OdooConfig(
            url="https://odoo.example",
            db="pinnacle_test",
            username="admin",
            password="secret",
        ),
        woo=WooConfig(
            url="http://localhost:8080",
            consumer_key="ck_test",
            consumer_secret="cs_test",
            api_version="wc/v3",
            verify_ssl=False,
            timeout=30,
        ),
        webhook=WebhookConfig(
            secret="wh_secret",
            path="/webhooks/woocommerce/orders",
            host="0.0.0.0",
            port=8000,
        ),
        runtime=RuntimeConfig(
            batch_size=50,
            max_retries=3,
            retry_delay=2.0,
            log_level="INFO",
            log_file="sync.log",
            state_file=".sync_state.json",
        ),
        watcher=WatcherConfig(interval=30, initial_full=True, state_file=".watch_snapshot.json"),
    )


def test_banner_muestra_objetivos_resueltos(monkeypatch, capsys):
    """Al arrancar, main() debe imprimir en stderr el Odoo URL, db y Woo URL resueltos."""
    monkeypatch.setattr("capuccino_vainilla.cli.load_config", lambda env_file=None: _fake_config())
    monkeypatch.setattr("capuccino_vainilla.cli.setup_logging", lambda *a, **kw: None)
    monkeypatch.setattr("capuccino_vainilla.cli._cmd_sync_catalog", lambda config, args: 0)

    rc = main(["sync-catalog"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "https://odoo.example" in captured.err
    assert "pinnacle_test" in captured.err
    assert "http://localhost:8080" in captured.err


def test_env_file_flag_se_pasa_a_load_config(monkeypatch):
    captured = {}

    def fake_load_config(env_file=None):
        captured["env_file"] = env_file
        raise ConfigError("stop")  # corta el flujo apenas capturamos

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", fake_load_config)
    rc = main(["--env-file", ".env.test", "sync-catalog"])

    assert captured["env_file"] == ".env.test"
    assert rc == 2  # main mapea ConfigError -> 2


def test_sin_env_file_se_usa_none(monkeypatch):
    captured = {}

    def fake_load_config(env_file=None):
        captured["env_file"] = env_file
        raise ConfigError("stop")

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", fake_load_config)
    main(["sync-catalog"])

    assert captured["env_file"] is None


def test_watch_once_corre_un_ciclo(monkeypatch):
    from capuccino_vainilla import cli

    monkeypatch.setattr("capuccino_vainilla.cli.load_config", lambda env_file=None: _fake_config())
    monkeypatch.setattr("capuccino_vainilla.cli.setup_logging", lambda *a, **kw: None)

    calls = {"run_once": 0}

    class FakeWatchService:
        def __init__(self, *a, **kw):
            pass

        def run_once(self):
            calls["run_once"] += 1

    # Evita construir clientes reales y el server.
    monkeypatch.setattr("capuccino_vainilla.services.connector.OdooWooConnector",
                        lambda *a, **kw: type("C", (), {"odoo": object(), "catalog": object()})())
    monkeypatch.setattr("capuccino_vainilla.watcher.service.WatchService", FakeWatchService)

    rc = cli.main(["watch", "--once"])

    assert rc == 0
    assert calls["run_once"] == 1
