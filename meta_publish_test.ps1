$ErrorActionPreference = "Stop"

$url = "https://web-production-448c1.up.railway.app/api/meta-advantage/publish"
$payload = @{
    variant_id   = "A"
    headline     = "Plant-based. No polyester."
    primary_text = "Activewear that breathes better in Indian heat."
    image_url    = "https://drive.google.com/uc?export=view&id=1grctlty9fwk5nCy4Jqu-URSpKnX1Xx77"
    cta          = "Shop Now"
    daily_budget = 200
}

while ($true) {
    try {
        $response = Invoke-RestMethod `
            -Method Post `
            -Uri $url `
            -ContentType "application/json" `
            -Body ($payload | ConvertTo-Json -Depth 5)

        if ($null -ne $response -and $response.ok -eq $true) {
            Write-Host "SUCCESS" -ForegroundColor Green
            Write-Host ("campaign_id: {0}" -f $response.campaign_id)
            Write-Host ("adset_id: {0}" -f $response.adset_id)
            Write-Host ("ad_id: {0}" -f $response.ad_id)
            break
        }

        $errorMessage = $null
        if ($null -ne $response.error) {
            $errorMessage = [string]$response.error
        } else {
            $errorMessage = "Unknown error returned from API."
        }

        Write-Host ("ERROR: {0}" -f $errorMessage) -ForegroundColor Red

        $clipboardText = "Fix this error in app.py: $errorMessage"
        Set-Clipboard -Value $clipboardText
        Write-Host "Copied fix prompt to clipboard."
    }
    catch {
        $cleanError = $_.Exception.Message

        # Try to extract cleaner server-side message if available.
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            try {
                $serverPayload = $_.ErrorDetails.Message | ConvertFrom-Json
                if ($serverPayload.error) {
                    $cleanError = [string]$serverPayload.error
                } else {
                    $cleanError = [string]$_.ErrorDetails.Message
                }
            }
            catch {
                $cleanError = [string]$_.ErrorDetails.Message
            }
        }

        Write-Host ("ERROR: {0}" -f $cleanError) -ForegroundColor Red

        $clipboardText = "Fix this error in app.py: $cleanError"
        Set-Clipboard -Value $clipboardText
        Write-Host "Copied fix prompt to clipboard."
    }

    Write-Host "Retrying in 90 seconds..."
    Start-Sleep -Seconds 90
}
$ErrorActionPreference = "Stop"

$endpoint = "https://web-production-448c1.up.railway.app/api/meta-advantage/publish"
$payload = @{
    variant_id   = "A"
    headline     = "Plant-based. No polyester."
    primary_text = "Activewear that breathes better in Indian heat."
    image_url    = "https://drive.google.com/uc?export=view&id=1grctlty9fwk5nCy4Jqu-URSpKnX1Xx77"
    cta          = "Shop Now"
    daily_budget = 200
}

function Get-CleanErrorMessage {
    param(
        [Parameter(Mandatory = $true)]
        [object]$ResponseObject
    )

    if ($null -eq $ResponseObject) {
        return "Unknown error: empty response."
    }

    if ($ResponseObject.error) {
        return [string]$ResponseObject.error
    }

    if ($ResponseObject.message) {
        return [string]$ResponseObject.message
    }

    return ($ResponseObject | ConvertTo-Json -Depth 10 -Compress)
}

while ($true) {
    try {
        $bodyJson = $payload | ConvertTo-Json -Depth 10 -Compress
        Write-Host "Calling $endpoint ..." -ForegroundColor Cyan

        $response = Invoke-RestMethod -Method Post -Uri $endpoint -ContentType "application/json" -Body $bodyJson

        $hasCampaignId = -not [string]::IsNullOrWhiteSpace([string]$response.campaign_id)
        if (($response.ok -eq $true) -or $hasCampaignId) {
            Write-Host "SUCCESS" -ForegroundColor Green
            Write-Host ("campaign_id: {0}" -f $response.campaign_id)
            Write-Host ("adset_id:    {0}" -f $response.adset_id)
            Write-Host ("ad_id:       {0}" -f $response.ad_id)
            Write-Host "NOTE: Delete duplicate test campaigns named 'WEARTH Meta A 177...' manually in Meta Ads Manager." -ForegroundColor Yellow
            break
        }

        $errorMsg = Get-CleanErrorMessage -ResponseObject $response
        Write-Host ("ERROR: {0}" -f $errorMsg) -ForegroundColor Red

        $cursorMsg = "Fix this error in app.py: $errorMsg"
        $cursorMsg | Set-Clipboard
        Write-Host "Copied fix request to clipboard for Cursor AI." -ForegroundColor Yellow
    }
    catch {
        $errorMsg = $_.Exception.Message

        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            try {
                $parsed = $_.ErrorDetails.Message | ConvertFrom-Json
                $errorMsg = Get-CleanErrorMessage -ResponseObject $parsed
            }
            catch {
                $errorMsg = $_.ErrorDetails.Message
            }
        }

        Write-Host ("ERROR: {0}" -f $errorMsg) -ForegroundColor Red
        $cursorMsg = "Fix this error in app.py: $errorMsg"
        $cursorMsg | Set-Clipboard
        Write-Host "Copied fix request to clipboard for Cursor AI." -ForegroundColor Yellow
    }

    Write-Host "Retrying in 90 seconds..." -ForegroundColor DarkYellow
    Start-Sleep -Seconds 90
}
