param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3 -m venv .venv
}
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip | Out-Null
& $Py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }

if (-not $SkipTests) {
    & $Py -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "tests failed - not building" }
}

& $Py -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\voxagen.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Report = Join-Path $Root "dist\selftest.json"
$p = Start-Process -FilePath "dist\VoxaGEN\VoxaGEN.exe" -ArgumentList "--selftest", "`"$Report`"" -Wait -PassThru
if ($p.ExitCode -ne 0) { Get-Content $Report; throw "packaged self-test failed" }
Write-Host "Self-test passed:" (Get-Content $Report -Raw)

$Version = (& $Py -c "import voxagen; print(voxagen.__version__)").Trim()
$Zip = "dist\VoxaGEN-$Version-win64.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path "dist\VoxaGEN\*" -DestinationPath $Zip
Write-Host "Built $Zip"
