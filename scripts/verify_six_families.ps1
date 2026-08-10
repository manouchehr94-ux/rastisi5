<#
.SYNOPSIS
    Reproducible verification for the six new storefront families
    (atlas_catalog, ava_fashion, toranj_gifting, sarv_stock,
    sepidar_handmade, zarrin_jewelry) plus regression coverage for the
    five existing families and cart/tenant-isolation/stock/gift-wrap
    checks.

.DESCRIPTION
    This script is a HANDOFF MECHANISM, not evidence that anything has
    passed. It must be run in a real Windows environment with Python and
    Django actually installed (this sandbox has neither — see
    SIX_NEW_FAMILIES_IMPLEMENTATION_REPORT.md for the exhaustive,
    documented attempt log proving Django could not be installed here).

    It uses the repository's OWN existing setup convention: a standard
    Python virtualenv + `requirements.txt` + `manage.py`. It does not
    invent a new parallel runtime, container, or CI system.

    Every gate below either exits non-zero on failure (system checks,
    migrations, unit/integration tests) or is a manual/Playwright-driven
    visual step that writes evidence files for you to inspect (screenshots
    are NEVER auto-approved by this script — a human must look at them).

.PARAMETER SkipBrowserTests
    Skip the Playwright browser/E2E section (steps 7-8) if a browser
    runtime is not available on this machine. All Django-level checks
    still run.

.EXAMPLE
    From D:\Projects\RastiSi4 :
        powershell -ExecutionPolicy Bypass -File .\scripts\verify_six_families.ps1

.EXAMPLE
    Skip browser tests (Django-only run):
        powershell -ExecutionPolicy Bypass -File .\scripts\verify_six_families.ps1 -SkipBrowserTests
#>

param(
    [switch]$SkipBrowserTests
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot | Split-Path -Parent
Set-Location $RepoRoot

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportDir = Join-Path $RepoRoot "scripts\.verify_output\six_families_$Timestamp"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$ReportFile = Join-Path $ReportDir "REPORT.md"
$ScreenshotDir = Join-Path $ReportDir "screenshots"
New-Item -ItemType Directory -Force -Path $ScreenshotDir | Out-Null

$global:AnyFailure = $false
$global:Results = @()

function Write-Section($title) {
    Write-Host ""
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

function Invoke-Gate {
    param(
        [string]$Name,
        [string]$Command,
        [switch]$AllowFailure
    )
    Write-Host "-> $Name" -ForegroundColor Yellow
    Write-Host "   $Command" -ForegroundColor DarkGray
    $output = & cmd /c "$Command 2>&1"
    $exitCode = $LASTEXITCODE
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    if ($exitCode -ne 0 -and -not $AllowFailure) {
        $global:AnyFailure = $true
    }
    $global:Results += [PSCustomObject]@{
        Gate = $Name
        Command = $Command
        ExitCode = $exitCode
        Status = $status
    }
    $output | Out-File -FilePath (Join-Path $ReportDir "$($Name -replace '[^\w\-]', '_').log") -Encoding utf8
    if ($exitCode -eq 0) {
        Write-Host "   OK" -ForegroundColor Green
    } else {
        Write-Host "   FAILED (exit $exitCode) — see log in $ReportDir" -ForegroundColor Red
    }
    return $exitCode
}

Write-Section "0. Environment"
Invoke-Gate -Name "python-version" -Command "python --version"
Invoke-Gate -Name "pip-freeze" -Command "pip freeze > `"$ReportDir\pip-freeze.txt`""

# --------------------------------------------------------------------------
# 1. Repository's own dependency method — venv + requirements.txt.
#    Does NOT invent a new environment manager. Skips venv creation if one
#    named .venv already exists and is activated (idempotent re-run).
# --------------------------------------------------------------------------
Write-Section "1. Environment setup (repository's existing convention)"
if (-not (Test-Path ".venv")) {
    Invoke-Gate -Name "create-venv" -Command "python -m venv .venv"
}
$activate = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $activate) {
    . $activate
}
Invoke-Gate -Name "install-requirements" -Command "pip install -r requirements.txt"

# --------------------------------------------------------------------------
# 2. Django system checks
# --------------------------------------------------------------------------
Write-Section "2. Django system checks"
Invoke-Gate -Name "manage-check" -Command "python manage.py check"

# --------------------------------------------------------------------------
# 3. Migration consistency
# --------------------------------------------------------------------------
Write-Section "3. Migration consistency"
Invoke-Gate -Name "makemigrations-check" -Command "python manage.py makemigrations --check --dry-run --noinput"
Invoke-Gate -Name "migrate-plan" -Command "python manage.py migrate --plan"

# --------------------------------------------------------------------------
# 4. Targeted six-family tests
# --------------------------------------------------------------------------
Write-Section "4. Six-family targeted tests"
Invoke-Gate -Name "test-eleven-families" -Command "python manage.py test apps.storefront_builder.tests.test_eleven_families --verbosity 2"
Invoke-Gate -Name "test-template-syntax-integrity" -Command "python manage.py test apps.storefront_builder.tests.test_template_syntax_integrity --verbosity 2"
Invoke-Gate -Name "test-six-families-tenant-isolation" -Command "python manage.py test apps.storefront_builder.tests.test_six_families_tenant_isolation --verbosity 2"

# --------------------------------------------------------------------------
# 5. Existing five-family regression
# --------------------------------------------------------------------------
Write-Section "5. Five-family regression"
Invoke-Gate -Name "test-family-heritage-premium" -Command "python manage.py test apps.storefront_builder.tests.test_family_heritage_premium --verbosity 2"
Invoke-Gate -Name "test-family-artisan-editorial" -Command "python manage.py test apps.storefront_builder.tests.test_family_artisan_editorial --verbosity 2"
Invoke-Gate -Name "test-family-nordic-living" -Command "python manage.py test apps.storefront_builder.tests.test_family_nordic_living --verbosity 2"
Invoke-Gate -Name "test-family-vibrant-catalog" -Command "python manage.py test apps.storefront_builder.tests.test_family_vibrant_catalog --verbosity 2"
Invoke-Gate -Name "test-family-registry" -Command "python manage.py test apps.storefront_builder.tests.test_family_registry --verbosity 2"

# --------------------------------------------------------------------------
# 6. Cart, stock enforcement, gift wrap, tenant-isolation tests
# --------------------------------------------------------------------------
Write-Section "6. Cart / stock / gift-wrap / tenant-isolation tests"
Invoke-Gate -Name "test-cart-security" -Command "python manage.py test apps.cart.tests.test_cart_security --verbosity 2"
Invoke-Gate -Name "test-cart-service" -Command "python manage.py test apps.cart.tests.test_cart_service --verbosity 2"
Invoke-Gate -Name "test-cart-views" -Command "python manage.py test apps.cart.tests.test_cart_views --verbosity 2"
Invoke-Gate -Name "test-cart-gift-wrap" -Command "python manage.py test apps.cart.tests.test_gift_wrap --verbosity 2"
Invoke-Gate -Name "test-settings-gift-wrap" -Command "python manage.py test apps.dashboard.tests.test_settings_views.SettingsGiftWrapViewTests --verbosity 2"
Invoke-Gate -Name "test-catalog-store-boundary" -Command "python manage.py test apps.orders.tests.test_catalog_store_boundary --verbosity 2"

# --------------------------------------------------------------------------
# 7. Start dev server for browser tests (skipped if -SkipBrowserTests)
# --------------------------------------------------------------------------
$devServerJob = $null
if (-not $SkipBrowserTests) {
    Write-Section "7. Starting Django dev server for browser/E2E tests"
    $devServerJob = Start-Job -ScriptBlock {
        param($root)
        Set-Location $root
        python manage.py runserver 0.0.0.0:8765
    } -ArgumentList $RepoRoot
    Start-Sleep -Seconds 5
    Write-Host "Dev server started as background job (Id=$($devServerJob.Id))" -ForegroundColor Green

    # ----------------------------------------------------------------------
    # 8. Browser/E2E tests + required screenshots
    #    Requires the `playwright` package + a Chromium build. Uses the
    #    existing scripts/verify_product_entry_ui.py pattern as the
    #    established convention for browser verification in this repo.
    # ----------------------------------------------------------------------
    Write-Section "8. Browser/E2E tests and required screenshots"
    Write-Host "NOTE: this step requires a store already configured with each" -ForegroundColor DarkYellow
    Write-Host "of the six new families published, reachable at the hosts your" -ForegroundColor DarkYellow
    Write-Host "local settings resolve to a real Store. Adjust RASTISI_VERIFY_BASE" -ForegroundColor DarkYellow
    Write-Host "and per-family hostnames before relying on this step's output." -ForegroundColor DarkYellow

    $env:RASTISI_SCREENSHOT_OUT = $ScreenshotDir
    Invoke-Gate -Name "browser-six-families" -Command "python scripts\verify_six_families_visual.py" -AllowFailure

    if ($devServerJob) {
        Stop-Job $devServerJob -ErrorAction SilentlyContinue
        Remove-Job $devServerJob -ErrorAction SilentlyContinue
    }
} else {
    Write-Section "7-8. Browser/E2E tests SKIPPED (-SkipBrowserTests)"
}

# --------------------------------------------------------------------------
# 9. Write timestamped evidence report
# --------------------------------------------------------------------------
Write-Section "9. Writing evidence report"

$reportLines = @()
$reportLines += "# Six New Families Verification Report"
$reportLines += ""
$reportLines += "Generated: $Timestamp"
$reportLines += "Repository root: $RepoRoot"
$reportLines += ""
$reportLines += "| Gate | Command | Exit Code | Status |"
$reportLines += "|---|---|---|---|"
foreach ($r in $global:Results) {
    $reportLines += "| $($r.Gate) | ``$($r.Command)`` | $($r.ExitCode) | $($r.Status) |"
}
$reportLines += ""
if ($global:AnyFailure) {
    $reportLines += "## OVERALL RESULT: FAILED — at least one mandatory gate did not pass."
} else {
    $reportLines += "## OVERALL RESULT: ALL MANDATORY GATES PASSED (Django-level)."
    $reportLines += ""
    $reportLines += "This does NOT mean visual/browser verification passed —"
    $reportLines += "screenshots in $ScreenshotDir must still be reviewed by a human."
}
$reportLines += ""
$reportLines += "## Required screenshots (visual review still needed by a human)"
$reportLines += ""
$reportLines += "For each of the six new families, at both viewports:"
$reportLines += ""
$reportLines += "* Home at 1440x1000"
$reportLines += "* Product at 1440x1000"
$reportLines += "* Home at 390x844"
$reportLines += "* Product at 390x844"
$reportLines += ""
$reportLines += "24 screenshots total. Check $ScreenshotDir for actual captures produced"
$reportLines += "by scripts\verify_six_families_visual.py (if it was created and run) —"
$reportLines += "this orchestration script does not itself render or approve any image."

$reportLines | Out-File -FilePath $ReportFile -Encoding utf8

Write-Host ""
Write-Host "Report written to: $ReportFile" -ForegroundColor Cyan

if ($global:AnyFailure) {
    Write-Host "RESULT: FAILED — see $ReportFile" -ForegroundColor Red
    exit 1
} else {
    Write-Host "RESULT: All mandatory Django-level gates passed. Visual review still required." -ForegroundColor Green
    exit 0
}
