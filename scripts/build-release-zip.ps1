# Build Windows download ZIP for GitHub Releases (no .git, no user recordings)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$outDir = Join-Path $root "dist"
$stage = Join-Path $outDir "MiX-Stream-Recorder"
$zip = Join-Path $outDir "MiX-Stream-Recorder-Windows.zip"

if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
if (Test-Path $zip) { Remove-Item -Force $zip }
New-Item -ItemType Directory -Path $stage | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage "recordings") | Out-Null

$files = @(
  "app.py", "capture.py", "encoder.py", "requirements.txt",
  "run.bat", "START-HERE.txt", "LICENSE", "README.md", "SECURITY.md",
  "smoke_test.py", "__init__.py"
)
foreach ($f in $files) {
  $src = Join-Path $root $f
  if (Test-Path $src) { Copy-Item $src (Join-Path $stage $f) }
}
Set-Content -Path (Join-Path $stage "recordings\.gitkeep") -Value "" -Encoding ascii

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force
Write-Host "ZIP: $zip"
Write-Host ("Size: {0:N1} KB" -f ((Get-Item $zip).Length / 1KB))
