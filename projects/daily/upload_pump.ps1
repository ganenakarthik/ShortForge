$ErrorActionPreference = "Continue"
$root = "C:\Users\ganen\youtube-team\OpenMontage"
$py = "$root\.venv\Scripts\python.exe"
$logDir = "$root\projects\daily\queue"
$queuePath = "$logDir\publish_queue.json"
$lockFile = "$logDir\run.lock"
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$logFile = "$logDir\upload_$stamp.log"
$env:YT_PRIVACY = "public"

# Only runs when the laptop is on (schtasks), so: if we're here we're awake.
# The internet check is the real gate — upload only when connected.
$online = $false
try {
    $online = [bool](Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet -ErrorAction Stop)
} catch { $online = $false }
if (-not $online) { exit 0 }

# Skip while a production run holds the lock (it uploads its own queue).
if (Test-Path $lockFile) {
    $lockAgeMin = ((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalMinutes
    if ($lockAgeMin -lt 90) { exit 0 }
}

if (-not (Test-Path $queuePath)) { exit 0 }
try {
    $queue = Get-Content $queuePath -Raw | ConvertFrom-Json
} catch { exit 0 }

$ready = @($queue | Where-Object { $_.status -eq "ready" -and $_.file })
if ($ready.Count -eq 0) { exit 0 }

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') uploading $($ready.Count) queued short(s)" | Out-File $logFile -Append
& $py "$root\projects\daily\upload_youtube.py" *>> $logFile