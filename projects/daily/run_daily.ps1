$ErrorActionPreference = "Continue"
$root = "C:\Users\ganen\youtube-team\OpenMontage"
$py = "$root\.venv\Scripts\python.exe"
$logDir = "$root\projects\daily\queue"
$queuePath = "$logDir\publish_queue.json"
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$logFile = "$logDir\run_$stamp.log"
$today = Get-Date -Format "yyyy-MM-dd"
$env:YT_PRIVACY = "public"
$retrySeconds = 300
$finalRetry = Get-Date (Get-Date -Hour 23 -Minute 30 -Second 0)

function Test-TodayUploaded {
    if (-not (Test-Path $queuePath)) { return $false }
    try {
        $queue = Get-Content $queuePath -Raw | ConvertFrom-Json
    } catch { return $false }
    $todayEntries = @($queue | Where-Object { $_.date -eq $today })
    if ($todayEntries.Count -lt 2) { return $false }
    foreach ($e in $todayEntries) {
        if ($e.status -ne "uploaded" -or -not $e.video_id) { return $false }
    }
    return $true
}

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Write-Output $line | Out-File $logFile -Append
}

if (Test-TodayUploaded) {
    Write-Log "already uploaded $today ; nothing to do."
    exit 0
}

$attempt = 0
while ($true) {
    $attempt++
    $runLog = "$logDir\run_$stamp.log"
    if (Test-TodayUploaded) {
        Write-Log "upload confirmed for $today (attempt $attempt even stopped)."
        exit 0
    }
    & $py "$root\projects\daily\daily_production.py" --count 3 --news 2 *>> $runLog
    $prodOk = ($LASTEXITCODE -eq 0)
    if ($prodOk -and (Test-Path "$root\projects\daily\client_secret.json")) {
        & $py "$root\projects\daily\upload_youtube.py" *>> $runLog
    }
    if (Test-TodayUploaded) {
        Write-Log "success: $today produced and uploaded (attempt $attempt)."
        exit 0
    }
    if ((Get-Date) -ge $finalRetry) {
        Write-Log "FAILED: could not produce+upload $today by 23:30 (attempt $attempt). Manual fix needed."
        exit 1
    }
    Write-Log "attempt $attempt failed (offline or transient?) - retrying in ${retrySeconds}s."
    Start-Sleep -Seconds $retrySeconds
}