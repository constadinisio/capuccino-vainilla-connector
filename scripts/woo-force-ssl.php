<?php
/**
 * MU-Plugin: permite que la REST API de WooCommerce use HTTP Basic Auth
 * sobre HTTP plano (localhost). Solo para el entorno de test local.
 *
 * WooCommerce llama a perform_basic_authentication() solo cuando is_ssl()
 * devuelve true; este hook lo fuerza para cada petición a la REST API.
 */
// Side-effect note: setting $_SERVER['HTTPS']='on' causes home_url()/site_url() to
// emit https:// URLs in REST _links responses. This is acceptable for local testing
// because the Odoo connector uses WOO_VERIFY_SSL=false and makes SKU/ID-based calls
// rather than following _links hrefs.
add_action( 'rest_api_init', function () {
    $_SERVER['HTTPS'] = 'on';
}, 1 );
