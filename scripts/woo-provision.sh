#!/usr/bin/env bash
# Aprovisiona el WooCommerce de prueba. Requiere el stack levantado:
#   docker compose --profile woo up -d woo-db woo
set -euo pipefail

WP="docker compose --profile woo run --rm -T woo-cli wp"

echo "==> Esperando a que WordPress acepte WP-CLI..."
until $WP db check >/dev/null 2>&1; do sleep 3; done

echo "==> Instalando el core de WordPress (idempotente)..."
$WP core install \
  --url="http://localhost:8080" \
  --title="Capuccino Vainilla TEST" \
  --admin_user="admin" \
  --admin_password="admin12345" \
  --admin_email="admin@example.com" \
  --skip-email || true

echo "==> Ajustando permisos de wp-content para el usuario woo-cli (uid 82)..."
MSYS_NO_PATHCONV=1 docker compose --profile woo exec -T woo chmod -R 777 /var/www/html/wp-content

echo "==> Instalando y activando WooCommerce..."
$WP plugin install woocommerce --activate

echo "==> Instalando mu-plugin para Basic Auth sobre HTTP..."
MSYS_NO_PATHCONV=1 docker compose --profile woo exec woo mkdir -p /var/www/html/wp-content/mu-plugins
docker compose --profile woo cp scripts/woo-force-ssl.php woo:/var/www/html/wp-content/mu-plugins/woo-force-ssl.php

echo "==> Fijando permalinks 'pretty' (requerido por la REST API)..."
# MSYS_NO_PATHCONV=1 evita que Git Bash en Windows convierta /%postname%/ a una ruta Windows
MSYS_NO_PATHCONV=1 $WP rewrite structure '/%postname%/' --hard
$WP rewrite flush --hard

echo "==> Generando una API key REST (read_write)..."
docker compose --profile woo cp scripts/woo-create-apikey.php woo:/var/www/html/woo-create-apikey.php
MSYS_NO_PATHCONV=1 $WP eval-file /var/www/html/woo-create-apikey.php

echo "==> Listo. Copiá el ck_/cs_ de arriba a tu .env.test (WOO_CONSUMER_KEY / WOO_CONSUMER_SECRET)."
