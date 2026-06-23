<#
.SYNOPSIS
    Monta el ENTORNO DE PRUEBA completo del conector, de punta a punta.

.DESCRIPTION
    Orquesta todo el flujo de test local de forma interactiva:
      1. Verifica prerequisitos (Docker, Python/venv, Git Bash).
      2. Levanta los contenedores (Odoo 16 + WooCommerce) con Docker.
      3. Crea la base de Odoo + usuario admin (pregunta los datos).
      4. Instala el modulo `stock` en Odoo.
      5. Aprovisiona WooCommerce y obtiene las claves REST (ck/cs).
      6. Escribe el archivo .env.local con todo lo necesario.
      7. (Opcional) Crea el webhook de pedidos en WooCommerce.
      8. (Opcional) Pobla el catalogo de Odoo con el seeder.

    Es IDEMPOTENTE en lo posible: re-correrlo no recrea la base ni el modulo si ya estan.

    *** SOLO PARA PRUEBAS LOCALES. *** Todo apunta a localhost. Nunca usar contra produccion.

.EXAMPLE
    .\scripts\setup-test.ps1

.NOTES
    Correr parado en la raiz del repo, con el .venv activado.
#>

[CmdletBinding()]
param(
    [string]$EnvFile = ".env.local"
)

$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------- #
#  Utilidades de salida
# --------------------------------------------------------------------------- #
function Write-Step  ($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok    ($m) { Write-Host "    [OK] $m" -ForegroundColor Green }
function Write-Warn  ($m) { Write-Host "    [!]  $m" -ForegroundColor Yellow }
function Write-Err   ($m) { Write-Host "    [X]  $m" -ForegroundColor Red }

function Read-Default ($prompt, $default) {
    $value = Read-Host "$prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $default }
    return $value
}

function Confirm-YesNo ($prompt, $defaultYes = $true) {
    $hint = if ($defaultYes) { "S/n" } else { "s/N" }
    $value = Read-Host "$prompt [$hint]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $defaultYes }
    return $value -match '^(s|si|sí|y|yes)$'
}

# Ruta al python del .venv (exista o no todavia).
function Get-VenvPython {
    return Join-Path (Get-Location) ".venv\Scripts\python.exe"
}

# --------------------------------------------------------------------------- #
#  0. Prerequisitos
# --------------------------------------------------------------------------- #
Write-Host "================================================================" -ForegroundColor Magenta
Write-Host "  Capuccino Vainilla - Setup del ENTORNO DE PRUEBA (local)" -ForegroundColor Magenta
Write-Host "  *** Todo apunta a localhost. No usar contra produccion. ***" -ForegroundColor Magenta
Write-Host "================================================================" -ForegroundColor Magenta

Write-Step "Verificando prerequisitos"

if (-not (Test-Path "docker-compose.yml")) {
    Write-Err "No encuentro docker-compose.yml. Corre el script desde la raiz del repo."
    exit 1
}
Write-Ok "Raiz del repo detectada."

foreach ($cmd in @("docker", "bash")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Err "Falta '$cmd' en el PATH. (bash viene con Git Bash.)"
        exit 1
    }
}
# --- Python + .venv + instalacion del conector (todo automatico) ---
$python = Get-VenvPython
if (-not (Test-Path $python)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Err "No encuentro 'python' en el PATH para crear el .venv. Instala Python 3.10+."
        exit 1
    }
    Write-Step "Creando el entorno virtual (.venv)"
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Err "No se pudo crear el .venv."; exit 1 }
    Write-Ok ".venv creado."
}
& $python --version | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Err "El Python del .venv no responde."; exit 1 }

# Instala el conector si todavia no esta en el .venv (idempotente).
& $python -c "import capuccino_vainilla" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Step "Instalando el conector en el .venv (pip install -e .[dev])"
    & $python -m pip install --upgrade pip | Out-Null
    & $python -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { Write-Err "Fallo 'pip install -e .[dev]'. Revisa la salida."; exit 1 }
    Write-Ok "Conector instalado."
} else {
    Write-Ok "Conector ya instalado en el .venv."
}

# Rutas a los entrypoints del .venv: funcionan SIN tener que activar el venv.
$cliExe  = Join-Path (Get-Location) ".venv\Scripts\capuccino-vainilla.exe"
$seedExe = Join-Path (Get-Location) ".venv\Scripts\seed-odoo.exe"

Write-Ok "Docker, bash y Python disponibles ($python)."

try { docker info 2>$null | Out-Null } catch {}
if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker no responde. Abri Docker Desktop y espera a que este 'running'."
    exit 1
}
Write-Ok "Docker esta corriendo."

# --------------------------------------------------------------------------- #
#  Recoleccion de inputs (todo de una, antes de empezar)
# --------------------------------------------------------------------------- #
Write-Step "Datos del entorno (Enter = valor por defecto)"

$odooDb       = Read-Default "Nombre de la base de Odoo"        "capuccino_test"
$odooLogin    = Read-Default "Usuario admin de Odoo (email)"    "admin@example.com"
$odooPassword = Read-Default "Password admin de Odoo"           "admin"
$odooMaster   = Read-Default "Master password del database mgr" "admin"

$doSeed    = Confirm-YesNo "Poblar el catalogo de Odoo con el seeder (requiere .env.seed configurado)?" $false
$doWebhook = Confirm-YesNo "Crear el webhook de pedidos en WooCommerce?" $true

# Secreto del webhook (aleatorio).
$webhookSecret = & $python -c "import secrets; print(secrets.token_hex(32))"

$odooUrl = "http://localhost:8069"
$wooUrl  = "http://localhost:8080"

# --------------------------------------------------------------------------- #
#  1. Levantar contenedores
# --------------------------------------------------------------------------- #
Write-Step "Levantando contenedores (Odoo + WooCommerce)"
docker compose --profile odoo --profile woo up -d
if ($LASTEXITCODE -ne 0) { Write-Err "Fallo 'docker compose up'."; exit 1 }
Write-Ok "Contenedores arriba."

# --------------------------------------------------------------------------- #
#  2. Esperar y configurar Odoo
# --------------------------------------------------------------------------- #
Write-Step "Esperando a que Odoo responda"
& $python scripts/odoo_bootstrap.py --url $odooUrl wait --timeout 240
if ($LASTEXITCODE -ne 0) { Write-Err "Odoo no respondio a tiempo."; exit 1 }

Write-Step "Creando la base de Odoo + admin"
& $python scripts/odoo_bootstrap.py --url $odooUrl create-db `
    --db-name $odooDb --admin-login $odooLogin --admin-password $odooPassword `
    --master-pwd $odooMaster --lang "es_AR"
if ($LASTEXITCODE -ne 0) { Write-Err "No se pudo crear la base de Odoo."; exit 1 }
Write-Ok "Base de Odoo lista."

Write-Step "Instalando el modulo 'stock' en Odoo"
& $python scripts/odoo_bootstrap.py --url $odooUrl install-module `
    --db-name $odooDb --admin-login $odooLogin --admin-password $odooPassword --module "stock"
if ($LASTEXITCODE -ne 0) { Write-Err "No se pudo instalar el modulo 'stock'."; exit 1 }
Write-Ok "Modulo 'stock' instalado."

# --------------------------------------------------------------------------- #
#  3. Aprovisionar WooCommerce y capturar las claves
# --------------------------------------------------------------------------- #
Write-Step "Aprovisionando WooCommerce (WordPress + Woo + API key)"
$wooOutput = bash scripts/woo-provision.sh 2>&1
$wooOutput | ForEach-Object { Write-Host "    | $_" -ForegroundColor DarkGray }
if ($LASTEXITCODE -ne 0) { Write-Err "Fallo el aprovisionamiento de WooCommerce."; exit 1 }

$ck = ($wooOutput | Select-String -Pattern '^ck_[0-9a-fA-F]+$' | Select-Object -Last 1).ToString().Trim()
$cs = ($wooOutput | Select-String -Pattern '^cs_[0-9a-fA-F]+$' | Select-Object -Last 1).ToString().Trim()
if ([string]::IsNullOrWhiteSpace($ck) -or [string]::IsNullOrWhiteSpace($cs)) {
    Write-Err "No pude leer el ck_/cs_ de la salida de woo-provision.sh. Revisa el log de arriba."
    exit 1
}
Write-Ok "Claves REST obtenidas (ck_...$($ck.Substring($ck.Length-4)) / cs_...$($cs.Substring($cs.Length-4)))."

# --------------------------------------------------------------------------- #
#  4. Escribir el .env.local
# --------------------------------------------------------------------------- #
Write-Step "Escribiendo $EnvFile"
if (Test-Path $EnvFile) {
    $backup = "$EnvFile.bak"
    Copy-Item $EnvFile $backup -Force
    Write-Warn "Ya existia $EnvFile -> respaldado en $backup."
}

$envContent = @"
# ==============================================================================
#  ENTORNO DE PRUEBA - generado por scripts/setup-test.ps1 (NO es produccion)
# ==============================================================================

# --- ODOO local (Docker) ---
ODOO_URL=$odooUrl
ODOO_DB=$odooDb
ODOO_USERNAME=$odooLogin
ODOO_PASSWORD=$odooPassword

# --- WOOCOMMERCE local (Docker) ---
WOO_URL=$wooUrl
WOO_CONSUMER_KEY=$ck
WOO_CONSUMER_SECRET=$cs
WOO_API_VERSION=wc/v3
WOO_VERIFY_SSL=false

# --- WEBHOOK (Flujo 2) ---
WEBHOOK_SECRET=$webhookSecret
WEBHOOK_PATH=/webhooks/woocommerce/orders
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000

# --- Runtime ---
BATCH_SIZE=50
MAX_RETRIES=3
RETRY_DELAY=2
HTTP_TIMEOUT=30
LOG_LEVEL=DEBUG
LOG_FILE=sync-test.log
STATE_FILE=.sync_state.test.json
"@

Set-Content -Path $EnvFile -Value $envContent -Encoding UTF8
Write-Ok "$EnvFile escrito."

# --------------------------------------------------------------------------- #
#  5. (Opcional) Crear el webhook en WooCommerce
# --------------------------------------------------------------------------- #
if ($doWebhook) {
    Write-Step "Creando el webhook 'order.created' en WooCommerce"
    $deliveryUrl = "http://host.docker.internal:8000/webhooks/woocommerce/orders"
    $body = @{
        name         = "Conector Odoo (test)"
        topic        = "order.created"
        delivery_url = $deliveryUrl
        secret       = $webhookSecret
        status       = "active"
    } | ConvertTo-Json
    $pair = "{0}:{1}" -f $ck, $cs
    $auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "$wooUrl/wp-json/wc/v3/webhooks" `
            -Headers @{ Authorization = "Basic $auth" } `
            -ContentType "application/json" -Body $body
        Write-Ok "Webhook creado (id $($resp.id)) -> $deliveryUrl"
        Write-Warn "Recorda: para que el Flujo 2 funcione tenes que correr 'serve' (ver pasos finales)."
    } catch {
        Write-Warn "No se pudo crear el webhook automaticamente: $($_.Exception.Message)"
        Write-Warn "Podes crearlo a mano desde Woo -> Ajustes -> Avanzado -> Webhooks."
    }
}

# --------------------------------------------------------------------------- #
#  6. (Opcional) Poblar el catalogo con el seeder
# --------------------------------------------------------------------------- #
if ($doSeed) {
    Write-Step "Poblando el catalogo de Odoo (seed-odoo)"
    if (-not (Test-Path ".env.seed")) {
        Write-Warn "No existe .env.seed. Copia .env.seed.example -> .env.seed y completalo, despues corre 'seed-odoo'."
    } else {
        & $seedExe
        if ($LASTEXITCODE -ne 0) { Write-Warn "El seeder termino con errores. Revisa la salida." }
        else { Write-Ok "Catalogo poblado." }
    }
}

# --------------------------------------------------------------------------- #
#  Cierre
# --------------------------------------------------------------------------- #
Write-Host "`n================================================================" -ForegroundColor Green
Write-Host "  Entorno de prueba LISTO." -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host @"

Proximos pasos (activa el .venv y usa 'capuccino-vainilla' a secas,
o copia/pega tal cual estos comandos con la ruta del .venv):

  # (una vez) activar el entorno
  .venv\Scripts\Activate.ps1

  # Ver estado de conexion (ambos paneles en verde)
  .venv\Scripts\capuccino-vainilla --env-file $EnvFile viewer

  # Flujo 1 - catalogo Odoo -> Woo (acotado para validar rapido)
  .venv\Scripts\capuccino-vainilla --env-file $EnvFile sync-catalog --limit 5 --full

  # Flujo 2 - levantar el servidor de webhooks (en el host)
  .venv\Scripts\capuccino-vainilla --env-file $EnvFile serve

  # Apagar todo al terminar
  docker compose --profile odoo --profile woo down

Guia completa: docs/guia-prueba-test-local.md
"@ -ForegroundColor Gray
