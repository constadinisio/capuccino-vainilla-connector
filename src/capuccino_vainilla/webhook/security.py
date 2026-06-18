"""Validación de la firma HMAC-SHA256 de los webhooks de WooCommerce.

WooCommerce firma el cuerpo (raw body) del webhook con el secreto configurado y
envía el resultado en el header ``X-WC-Webhook-Signature`` como Base64.
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def compute_signature(body: bytes, secret: str) -> str:
    """Calcula la firma esperada (Base64 de HMAC-SHA256) para un cuerpo dado."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Verifica la firma del webhook en tiempo constante.

    Devuelve False si falta la firma o el secreto, o si no coincide.
    """
    if not signature or not secret:
        return False
    expected = compute_signature(body, secret)
    # compare_digest evita ataques de temporización.
    return hmac.compare_digest(expected, signature)
