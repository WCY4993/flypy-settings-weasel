[CmdletBinding()]
param([string]$Python='python')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
 & $Python -m pip install -r requirements-build.txt
 if($LASTEXITCODE){throw '安裝建置依賴失敗'}
 & $Python -m unittest discover -p 'test_public.py' -v
 if($LASTEXITCODE){throw '測試未通過'}
 & $Python -m PyInstaller --noconfirm --onefile --windowed --noupx --name '小鶴設定工具' --collect-data opencc --collect-submodules ruamel.yaml --icon app.ico --add-data 'app.ico;.' --add-data 'lua/flypy_learning.lua;lua' --add-data 'lua/flypy_number_style.lua;lua' --version-file version-info.txt flypy_settings.py
 if($LASTEXITCODE){throw '打包失敗'}
} finally {Pop-Location}
