"""Tests de la validación de firma HMAC del webhook."""

from __future__ import annotations

from capuccino_vainilla.webhook.security import compute_signature, verify_signature

SECRET = "super-secreto"
BODY = b'{"id": 1, "line_items": []}'


def test_roundtrip_valid_signature():
    signature = compute_signature(BODY, SECRET)
    assert verify_signature(BODY, signature, SECRET) is True


def test_wrong_secret_fails():
    signature = compute_signature(BODY, "otro-secreto")
    assert verify_signature(BODY, signature, SECRET) is False


def test_missing_signature_fails():
    assert verify_signature(BODY, None, SECRET) is False


def test_tampered_body_fails():
    signature = compute_signature(BODY, SECRET)
    assert verify_signature(b'{"id": 2}', signature, SECRET) is False
