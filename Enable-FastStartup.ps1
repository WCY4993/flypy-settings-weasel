# Run as the current user. No administrator privileges or global startup delays changed.
$ErrorActionPreference = 'Stop'
$approved = 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run'
$state = (Get-ItemProperty -LiteralPath $approved -Name WeaselServer -ErrorAction SilentlyContinue).WeaselServer
if (-not $state -or $state[0] -ne 3) {
    throw '請先在工作管理員的「啟動應用程式」停用原有 WeaselServer，再執行本工具，以免重複啟動。'
}
$destination = Join-Path $env:LOCALAPPDATA 'FlypySettings'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$helperPath = Join-Path $destination 'Start-WeaselIfNeeded.ps1'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Start-WeaselIfNeeded.ps1') -Destination $helperPath -Force
$shellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$action = New-ScheduledTaskAction -Execute $shellPath -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$helperPath+'"')
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
$principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'FlypySettings-WeaselStartup' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Output '已設定下次登入時啟動小狼毫；未啟動或重啟目前的服務。'
