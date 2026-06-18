<?php
/**
 * MU-Plugin: permite que la REST API de WooCommerce use HTTP Basic Auth
 * sobre HTTP plano (localhost). Solo para el entorno de test local.
 *
 * WooCommerce llama a perform_basic_authentication() solo cuando is_ssl()
 * devuelve true; este hook lo fuerza para cada petición a la REST API.
 */
add_action( 'rest_api_init', function () {
    $_SERVER['HTTPS'] = 'on';
}, 1 );
