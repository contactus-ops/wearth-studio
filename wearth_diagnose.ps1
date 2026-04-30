$BASE = "https://web-production-448c1.up.railway.app"
$PASS = @(); $FAIL = @(); $DETAILS = @()

function Test-Endpoint {
    param([string]$Name, [string]$Method="GET", [string]$Path, [hashtable]$Body=$null, [string]$ExpectKey="")
    $url = "$BASE$Path"
    try {
        if ($Method -eq "POST") {
            $resp = Invoke-WebRequest -Uri $url -Method POST -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 5) -UseBasicParsing -TimeoutSec 30
        } else {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
        }
        $parsed = $resp.Content | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($ExpectKey -and -not $parsed.$ExpectKey) {
            $script:FAIL += $Name
            $script:DETAILS += "  FAIL  $Name - missing key '$ExpectKey'"
            $script:DETAILS += "        Response: $($resp.Content.Substring(0,[Math]::Min(200,$resp.Content.Length)))"
        } else {
            $script:PASS += $Name
            $script:DETAILS += "  PASS  $Name"
        }
    } catch {
        $script:FAIL += $Name
        $script:DETAILS += "  FAIL  $Name - $($_.Exception.Message)"
        try {
            $s = $_.Exception.Response.GetResponseStream()
            $r = New-Object System.IO.StreamReader($s)
            $b = $r.ReadToEnd()
            $script:DETAILS += "        Body: $($b.Substring(0,[Math]::Min(300,$b.Length)))"
        } catch {}
    }
}

Write-Host ""
Write-Host "==== WEARTH DIAGNOSTIC $(Get-Date -Format 'HH:mm') ====" -ForegroundColor Cyan
Write-Host ""

Test-Endpoint -Name "Health"       -Path "/health"              -ExpectKey "status"
Test-Endpoint -Name "SEO Status"   -Path "/seo-status"          -ExpectKey "published"
Test-Endpoint -Name "Garments"     -Path "/api/garments"
Test-Endpoint -Name "Library"      -Path "/api/library"         -ExpectKey "photos"
Test-Endpoint -Name "Drive Videos" -Path "/api/drive/videos"    -ExpectKey "videos"
Test-Endpoint -Name "Meta Dry Run" -Method "POST" -Path "/api/meta-advantage/publish-test" -Body @{variant_id="DIAG";headline="Move in comfort.";primary_text="Plant-based activewear.";image_url="https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800";cta="Shop Now";daily_budget=200} -ExpectKey "ok"

Write-Host ""
foreach ($line in $DETAILS) {
    if ($line -match "PASS") { Write-Host $line -ForegroundColor Green }
    elseif ($line -match "FAIL") { Write-Host $line -ForegroundColor Red }
    else { Write-Host $line -ForegroundColor DarkGray }
}

Write-Host ""
Write-Host "PASSED: $($PASS.Count)  FAILED: $($FAIL.Count)" -ForegroundColor White

if ($FAIL.Count -gt 0) {
    $prompt = "WEARTH Flask app failures. FAILED: $($FAIL -join ', '). DETAILS: $(($DETAILS | Where-Object {$_ -match 'FAIL|Body|Response'}) -join ' | '). Find root cause in app.py and fix without breaking working endpoints."
    $prompt | Set-Clipboard
    Write-Host ""
    Write-Host "Fix prompt copied to clipboard - paste into Cursor." -ForegroundColor Yellow
}