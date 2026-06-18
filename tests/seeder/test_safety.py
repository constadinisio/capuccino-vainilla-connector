import pytest

from capuccino_vainilla.seeder.safety import (
    TargetNotLocalError,
    assert_local_target,
    confirmation_banner,
)


@pytest.mark.parametrize("url", [
    "http://localhost:8069",
    "http://127.0.0.1:8069",
    "http://odoo:8069",          # nombre de servicio docker
])
def test_assert_local_target_accepts_local(url):
    assert_local_target(url)  # no lanza


@pytest.mark.parametrize("url", [
    "https://capuccino-vainilla.odoo.com",
    "https://produccion.empresa.com",
])
def test_assert_local_target_rejects_remote(url):
    with pytest.raises(TargetNotLocalError):
        assert_local_target(url)


def test_confirmation_banner_mentions_both_urls():
    banner = confirmation_banner("http://localhost:8069", "https://real.odoo.com")
    assert "http://localhost:8069" in banner
    assert "https://real.odoo.com" in banner
