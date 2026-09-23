param([int]$Port = 18770, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$boardRepo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boardUrl = "http://127.0.0.1:$Port"
$healthy = $false
try {
    $state = Invoke-RestMethod "$boardUrl/api/health" -TimeoutSec 2
    if ($state.application -ne 'petsoul-live-blackboard' -or [IO.Path]::GetFullPath($state.repo) -ne $boardRepo) {
        throw 'Port belongs to another service or checkout.'
    }
    $healthy = $true
} catch {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "Port $Port is occupied; existing service left untouched. Choose another -Port."
    }
}
if (-not $healthy) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
    $runtime = Join-Path $boardRepo 'output\playwright\live-blackboard-runtime'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $script = Join-Path $PSScriptRoot 'serve_blackboard.py'
    $child = Start-Process -FilePath $python -ArgumentList @('-B', "`"$script`"", '--port', $Port) -WorkingDirectory $boardRepo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server.out.log') -RedirectStandardError (Join-Path $runtime 'server.err.log')
    Set-Content -LiteralPath (Join-Path $runtime 'server.pid') -Value $child.Id
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $state = Invoke-RestMethod "$boardUrl/api/health" -TimeoutSec 1
            if ($state.application -eq 'petsoul-live-blackboard' -and [IO.Path]::GetFullPath($state.repo) -eq $boardRepo) { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 150 }
    }
    if (-not $healthy) { throw "Board failed to start. See $runtime\server.err.log" }
}
Write-Output "PetSoul blackboard ready: $boardUrl"
if (-not $NoOpen) { Start-Process $boardUrl -WindowStyle Hidden }
