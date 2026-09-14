$env:PYTHONUTF8 = "1"
# Start server as background job
$job = Start-Job -ScriptBlock {
    Set-Location "c:\Users\hp\OneDrive\Desktop\ocianix\backend"
    $env:PYTHONUTF8 = "1"
    python -m uvicorn main:app --port 8001 --log-level info 2>&1
}
Start-Sleep -Seconds 6

function Test-Endpoint($label, $url) {
    Write-Host "=== $label ==="
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
        Write-Host "HTTP $($r.StatusCode)"
        # Pretty-print JSON
        $json = $r.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10
        Write-Host $json
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        Write-Host "HTTP $status - ERROR: $_"
    }
    Write-Host ""
}

# Test all endpoints
Test-Endpoint "GET /" "http://127.0.0.1:8001/"
Test-Endpoint "GET /api/system/status" "http://127.0.0.1:8001/api/system/status"
Test-Endpoint "GET /api/satellite/scenes" "http://127.0.0.1:8001/api/satellite/scenes"
Test-Endpoint "GET /api/satellite/samples" "http://127.0.0.1:8001/api/satellite/samples"
Test-Endpoint "GET /api/satellite/image (random)" "http://127.0.0.1:8001/api/satellite/image"
Test-Endpoint "GET /api/vessels/search?query=ARABIAN" "http://127.0.0.1:8001/api/vessels/search?query=ARABIAN"
Test-Endpoint "GET /api/vessels/area" "http://127.0.0.1:8001/api/vessels/area?min_lon=72.0&min_lat=8.0&max_lon=81.0&max_lat=22.0&start_time=2026-09-03T00:00:00Z&end_time=2026-09-03T12:00:00Z"
Test-Endpoint "GET /api/ais/stats" "http://127.0.0.1:8001/api/ais/stats"
Test-Endpoint "GET /docs" "http://127.0.0.1:8001/docs"

# Server logs
Write-Host "=== SERVER LOG ==="
Receive-Job -Job $job
Stop-Job $job
Remove-Job $job
