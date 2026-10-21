# Used by the per-user logon task. A duplicate WeaselServer launch restarts it.
$ErrorActionPreference = 'Stop'
$sessionId = (Get-Process -Id $PID).SessionId
if (Get-Process WeaselServer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $sessionId) { exit 0 }
$installPath = $null
foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32,[Microsoft.Win32.RegistryView]::Registry64)) {
    $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine,$view)
    try {
        $key = $base.OpenSubKey('SOFTWARE\Rime\Weasel')
        if ($key) { try { $installPath = $key.GetValue('WeaselRoot') } finally { $key.Dispose() } }
    } finally { $base.Dispose() }
    if ($installPath) { break }
}
if (-not $installPath) { throw 'Cannot locate the installed Weasel folder.' }
$serverPath = Join-Path $installPath 'WeaselServer.exe'
if (-not (Test-Path -LiteralPath $serverPath -PathType Leaf)) { throw 'Cannot locate WeaselServer.exe.' }
# Recheck immediately before launching; never restart a server already in use.
if (-not (Get-Process WeaselServer -ErrorAction SilentlyContinue | Where-Object SessionId -eq $sessionId)) {
    Start-Process -FilePath $serverPath -WindowStyle Hidden
}
