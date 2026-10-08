$ErrorActionPreference = 'Stop'

$base = 'http://127.0.0.1:18080/jdntqWFrZf.php/shop/v5/workspace'
$cookie = if ($env:HEALTHFLOW_TEST_SESSION) { "PHPSESSID=$($env:HEALTHFLOW_TEST_SESSION)" } else { 'PHPSESSID=codexv5final20260930' }
$pages = @(
    'dashboard', 'product', 'ingredients', 'recommendations', 'plans', 'purchases',
    'orders', 'batches', 'fulfillment', 'aftersales', 'suppliers', 'supplier_sku',
    'supplier_collaboration', 'delivery_rules', 'analytics', 'marketing', 'members',
    'settings', 'audit'
)

$pageFailures = @()
foreach ($page in $pages) {
    $body = (curl.exe -s -H "Cookie: $cookie" "$base/$page") -join "`n"
    if ($body -notmatch 'v5-workspace') {
        $pageFailures += $page
    }
}

$content = Get-Content -Raw application/admin/controller/shop/v5/Workspace.php
$resources = [regex]::Matches($content, "(?m)^\s*'([^']+)'\s*=>\s*\`$this->r\(") |
    ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
$dataFailures = @()
foreach ($resource in $resources) {
    $body = (curl.exe -s -G -H "Cookie: $cookie" --data-urlencode "resource=$resource" --data-urlencode 'limit=1' "$base/data") -join "`n"
    try {
        $json = $body | ConvertFrom-Json
        if ($null -eq $json.total -or $null -eq $json.rows) {
            $dataFailures += "$resource(shape)"
        }
    } catch {
        $dataFailures += "$resource(json)"
    }
}

$templatePath = Join-Path $env:TEMP 'healthflow-master-template-test.xlsx'
curl.exe -s -H "Cookie: $cookie" -o $templatePath "$base/downloadImportTemplate"
$bytes = [System.IO.File]::ReadAllBytes($templatePath)
$magic = [System.BitConverter]::ToString($bytes[0..3])

Write-Output "pages=$($pages.Count) page_failures=$($pageFailures -join ',')"
Write-Output "resources=$($resources.Count) data_failures=$($dataFailures -join ',')"
Write-Output "template_magic=$magic template_bytes=$($bytes.Length)"

if ($pageFailures.Count -or $dataFailures.Count -or $magic -ne '50-4B-03-04') {
    exit 1
}
