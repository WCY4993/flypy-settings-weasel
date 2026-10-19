[CmdletBinding()]
param([ValidateSet('Backup','Deploy','Sync','UpdateIce')][string]$Action='Backup')
$ErrorActionPreference='Stop'
$UserDir=(Get-ItemProperty 'HKCU:\Software\Rime\Weasel' -ErrorAction SilentlyContinue).RimeUserDir
if(-not $UserDir){$UserDir=Join-Path $env:APPDATA 'Rime'}
$UserDir=[IO.Path]::GetFullPath($UserDir)
$program=$null
foreach($key in @('HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel','HKLM:\SOFTWARE\Rime\Weasel')){
 $v=Get-ItemProperty $key -ErrorAction SilentlyContinue
 if($v.WeaselRoot){$program=$v.WeaselRoot;break}
}
if(-not $program -or -not(Test-Path -LiteralPath $UserDir)){throw '找不到小狼毫或目前使用者資料夾。'}
$server=Join-Path $program 'WeaselServer.exe';$deployer=Join-Path $program 'WeaselDeployer.exe'
& $server /quit
try{
 for($i=0;$i -lt 30 -and (Get-Process WeaselServer -ErrorAction SilentlyContinue);$i++){Start-Sleep -Milliseconds 200}
 if(Get-Process WeaselServer -ErrorAction SilentlyContinue){throw '小狼毫仍在執行，未進行維護。'}
 if($Action -in @('Backup','UpdateIce')){
  $backup=Join-Path $env:LOCALAPPDATA ('FlypySettings\full-backups\'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  Copy-Item -LiteralPath $UserDir -Destination (Join-Path $backup 'Rime') -Recurse
  & reg.exe export 'HKCU\Software\Rime' (Join-Path $backup 'Rime.reg') /y | Out-Null
  Write-Host "完整備份：$backup"
 }
 if($Action -eq 'UpdateIce'){
  $lock=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'upstream.json') -Raw | ConvertFrom-Json
  $stage=Join-Path ([IO.Path]::GetTempPath()) ('FlypyUpdate-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $stage | Out-Null
  $zip=Join-Path $stage 'ice.zip'
  Invoke-WebRequest "https://codeload.github.com/iDvel/rime-ice/zip/$($lock.commit)" -OutFile $zip
  if((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ine $lock.archive_sha256){throw '上游壓縮檔雜湊不符，未更新。'}
  Expand-Archive -LiteralPath $zip -DestinationPath $stage
  $source=Join-Path $stage "rime-ice-$($lock.commit)"
  $tool=Join-Path $env:LOCALAPPDATA 'Programs\FlypySettings\小鶴設定工具.exe'
  if(-not(Test-Path -LiteralPath $tool)){throw '找不到設定工具，未更新。'}
  $p=Start-Process -FilePath $tool -ArgumentList @('--refresh-flypy-patches',('"'+$source+'"'),('"'+$UserDir+'"')) -WindowStyle Hidden -Wait -PassThru
  if($p.ExitCode){throw '上游規則合併失敗，未覆蓋上游檔案。'}
  Get-ChildItem -LiteralPath $source -File -Filter '*.yaml' | Where-Object {$_.Name -notlike '*.custom.yaml' -and $_.Name -notlike 'flypy_*'} | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $UserDir -Force}
  foreach($folder in @('cn_dicts','en_dicts','lua','opencc')){
   $base=Join-Path $source $folder
   Get-ChildItem -LiteralPath $base -File -Recurse | ForEach-Object {
    $relative=$_.FullName.Substring($base.Length).TrimStart('\')
    if($_.Name -notlike 'flypy_*'){
     $target=Join-Path (Join-Path $UserDir $folder) $relative
     New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
     Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
   }
  }
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'upstream.json') -Destination (Join-Path $UserDir 'flypy-upstream.json') -Force
 }
 if($Action -in @('Deploy','UpdateIce','Sync')){
  $arg=if($Action -eq 'Sync'){'/sync'}else{'/deploy'}
  $p=Start-Process -FilePath $deployer -ArgumentList $arg -WindowStyle Hidden -Wait -PassThru
  if($p.ExitCode){throw "小狼毫維護失敗：$($p.ExitCode)；原資料與備份均保留。"}
  Write-Host '維護完成。'
 }
}finally{Start-Process -FilePath $server -WindowStyle Hidden}
