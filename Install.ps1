# Public clean install. Existing dictionaries and preferences are never merged.
[CmdletBinding()]
param([string]$UserDir = (Join-Path $env:APPDATA 'RimeFlypy'), [string]$WeaselRoot, [switch]$PrepareOnly)
$ErrorActionPreference='Stop'
$UserDir=[IO.Path]::GetFullPath($UserDir)
if(Test-Path -LiteralPath $UserDir){if(Get-ChildItem -LiteralPath $UserDir -Force | Select-Object -First 1){throw '目的地不是空白資料夾。請指定新的 -UserDir；既有設定不會被覆蓋。'}}
if(-not $WeaselRoot){
 foreach($key in @('HKLM:\SOFTWARE\WOW6432Node\Rime\Weasel','HKLM:\SOFTWARE\Rime\Weasel')){
  $v=Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
  if($v.WeaselRoot){$WeaselRoot=$v.WeaselRoot;break}
 }
}
if(-not $WeaselRoot -or -not(Test-Path -LiteralPath (Join-Path $WeaselRoot 'WeaselDeployer.exe'))){throw '請先從 https://github.com/rime/weasel/releases 安裝官方小狼毫。'}
$lock=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'upstream.json') -Raw | ConvertFrom-Json
$stage=Join-Path ([IO.Path]::GetTempPath()) ('FlypyInstall-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage | Out-Null
$bundled=Join-Path $PSScriptRoot 'upstream'
if(Test-Path -LiteralPath (Join-Path $bundled 'double_pinyin_flypy.schema.yaml')){$upstream=$bundled}else{
 $archive=Join-Path $stage 'ice.zip'
 Invoke-WebRequest -Uri "https://codeload.github.com/iDvel/rime-ice/zip/$($lock.commit)" -OutFile $archive
 if($lock.archive_sha256 -and (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $lock.archive_sha256){throw '上游壓縮檔 SHA-256 不符；未安裝。'}
 Expand-Archive -LiteralPath $archive -DestinationPath $stage
 $upstream=Join-Path $stage "rime-ice-$($lock.commit)"
}
if(-not(Test-Path -LiteralPath (Join-Path $upstream 'LICENSE'))){throw '上游資料不完整。'}
New-Item -ItemType Directory -Path $UserDir -Force | Out-Null
Get-ChildItem -LiteralPath $upstream -File -Filter '*.yaml' | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $UserDir}
foreach($folder in @('cn_dicts','en_dicts','lua','opencc')){Copy-Item -LiteralPath (Join-Path $upstream $folder) -Destination (Join-Path $UserDir $folder) -Recurse}
foreach($name in @('default.custom.yaml','weasel.custom.yaml','double_pinyin_flypy.custom.yaml','melt_eng.custom.yaml','radical_pinyin.custom.yaml','flypy_tw.dict.yaml','flypy_personal.dict.yaml','flypy_phrases.txt')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $UserDir}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'upstream.json') -Destination (Join-Path $UserDir 'flypy-upstream.json')
if($PrepareOnly){Write-Host "空白個人配置已備妥：$UserDir；尚未切換輸入法或部署。";return}
$key='HKCU:\Software\Rime\Weasel'
$old=(Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue).RimeUserDir
$backup=Join-Path $env:LOCALAPPDATA ('FlypySettings\install-backups\'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
@{previous_user_dir=$old;new_user_dir=$UserDir} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'paths.json') -Encoding utf8
& reg.exe export 'HKCU\Software\Rime' (Join-Path $backup 'Rime.reg') /y | Out-Null
$server=Join-Path $WeaselRoot 'WeaselServer.exe'
& $server /quit
try{
 New-Item -Path $key -Force | Out-Null
 Set-ItemProperty -LiteralPath $key -Name RimeUserDir -Value $UserDir
 $p=Start-Process -FilePath (Join-Path $WeaselRoot 'WeaselDeployer.exe') -ArgumentList '/deploy' -WindowStyle Hidden -Wait -PassThru
 if($p.ExitCode -ne 0){throw "部署失敗：$($p.ExitCode)"}
 $exe=Join-Path $PSScriptRoot '小鶴設定工具.exe'
 if(Test-Path -LiteralPath $exe){
  $program=Join-Path $env:LOCALAPPDATA 'Programs\FlypySettings'
  New-Item -ItemType Directory -Path $program -Force | Out-Null
  Copy-Item -LiteralPath $exe -Destination (Join-Path $program '小鶴設定工具.exe') -Force
  $shell=New-Object -ComObject WScript.Shell
  $link=$shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) '小鶴設定工具.lnk'))
  $link.TargetPath=Join-Path $program '小鶴設定工具.exe';$link.WorkingDirectory=$program;$link.Save()
 }
 Write-Host "安裝及部署完成：$UserDir。按 Win+Space 選小狼毫。舊資料仍保留在原位置。"
}catch{
 if($old){Set-ItemProperty -LiteralPath $key -Name RimeUserDir -Value $old}else{Remove-ItemProperty -LiteralPath $key -Name RimeUserDir -ErrorAction SilentlyContinue}
 throw
}finally{Start-Process -FilePath $server -WindowStyle Hidden}
