# Run as the current user. No administrator privileges or global startup delays changed.
$ErrorActionPreference = 'Stop'
$approved = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
$state = (Get-ItemProperty -LiteralPath $approved -Name WeaselServer -ErrorAction SilentlyContinue).WeaselServer
if (-not $state -or $state[0] -ne 3) {
    throw 'Disable the original WeaselServer startup item in Task Manager before enabling this task, to avoid duplicate starts.'
}
$destination = Join-Path $env:USERPROFILE '.flypy-settings'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$helperPath = Join-Path $destination 'WeaselStartup.exe'
$packaged = Join-Path $PSScriptRoot 'WeaselStartup.exe'
if (Test-Path -LiteralPath $packaged -PathType Leaf) {
    Copy-Item -LiteralPath $packaged -Destination $helperPath -Force
} else {
    $compiler = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    $source = Join-Path $PSScriptRoot 'WeaselStartup.cs'
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'The built startup helper is missing. Download the complete release package.' }
    & $compiler /nologo /target:winexe /optimize+ "/out:$helperPath" $source
    if ($LASTEXITCODE) { throw 'Startup helper compilation failed; task was not changed.' }
}
$action = New-ScheduledTaskAction -Execute $helperPath -WorkingDirectory $destination
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$settings.Priority = 4
$previous = Get-ScheduledTask -TaskName 'FlypySettings-WeaselStartup' -ErrorAction SilentlyContinue
if ($previous) {
    Export-ScheduledTask -TaskName 'FlypySettings-WeaselStartup' | Set-Content -LiteralPath (Join-Path $destination ('startup-task-backup-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.xml')) -Encoding Unicode
}
Register-ScheduledTask -TaskName 'FlypySettings-WeaselStartup' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output 'Weasel will start at next logon. The current service was not started or restarted.'
