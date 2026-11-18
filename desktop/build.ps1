# Builds AnexisSetup.exe. Run it on Windows, from the desktop folder:
#
#     powershell -ExecutionPolicy Bypass -File build.ps1
#
# You need Node 20 or newer and an internet connection. Nothing else: this
# script downloads the Python, Node and uv that go inside the installer.
#
# What ends up inside the installer:
#   runtime\python   a full Python with every package Anexis needs
#   runtime\node     Node, for the tool servers and Claude Code
#   runtime\uv.exe   uv and uvx, for the Python tool servers
#   source\          the app itself as plain files (anexis, ui, tools, ...)
#
# Output: dist\AnexisSetup.exe
#
#   -PythonVersion 3.12    which Python to ship
#   -NodeMajor 24          which Node line to ship
#   -SkipRuntime           reuse stage\runtime from the last build (much faster)

param(
    [string]$PythonVersion = "3.12",
    [int]$NodeMajor = 24,
    [switch]$SkipRuntime
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # downloads are many times faster without the progress bar

$Desktop = $PSScriptRoot
$Repo    = Split-Path $Desktop -Parent
$Stage   = Join-Path $Desktop "stage"
$Runtime = Join-Path $Stage "runtime"
$Source  = Join-Path $Stage "source"
$Tmp     = Join-Path $Stage "tmp"

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Run {
    # Runs a program and stops the build when it fails.
    $exe, $rest = $args
    & $exe @rest
    if ($LASTEXITCODE -ne 0) { throw "$exe failed with exit code $LASTEXITCODE" }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node is not installed. Get it from https://nodejs.org (20 or newer), then run this again."
}

New-Item -ItemType Directory -Force -Path $Stage, $Tmp | Out-Null

if (-not $SkipRuntime) {
    if (Test-Path $Runtime) { Remove-Item -Recurse -Force -LiteralPath $Runtime }
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

    Say "uv (the Python package tool that also ships inside the app)"
    $uvZip = Join-Path $Tmp "uv.zip"
    Invoke-WebRequest "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $uvZip
    Expand-Archive -Force -LiteralPath $uvZip -DestinationPath $Runtime
    $uv = Join-Path $Runtime "uv.exe"
    if (-not (Test-Path $uv)) { throw "uv.exe was not in the downloaded archive." }

    Say "Python $PythonVersion"
    $pyHome = Join-Path $Tmp "python"
    if (Test-Path $pyHome) { Remove-Item -Recurse -Force -LiteralPath $pyHome }
    Run $uv python install $PythonVersion --install-dir $pyHome
    # uv makes the real folder (cpython-3.12.x-...) and a short link to it. Take the real one.
    $found = Get-ChildItem -LiteralPath $pyHome -Directory |
        Where-Object { $_.Name -match "^cpython-\d+\.\d+\.\d+" -and -not $_.LinkType -and (Test-Path (Join-Path $_.FullName "python.exe")) } |
        Select-Object -First 1
    if (-not $found) { throw "uv installed Python but python.exe was not found under $pyHome" }
    # Copied, not linked: this folder is what the installer packs, and it has to work from any path.
    Copy-Item -Recurse -LiteralPath $found.FullName -Destination (Join-Path $Runtime "python")
    $python = Join-Path $Runtime "python\python.exe"
    # uv marks its Pythons "do not install into me". This one is ours to fill.
    Get-ChildItem -LiteralPath (Join-Path $Runtime "python") -Recurse -Filter "EXTERNALLY-MANAGED" | Remove-Item -Force

    Say "Python packages (the exact versions in uv.lock, plus desktop control)"
    $requirements = Join-Path $Tmp "requirements.txt"
    Push-Location $Repo
    try { Run $uv export --frozen --no-dev --no-emit-project --extra desktop --no-hashes --format requirements-txt -o $requirements }
    finally { Pop-Location }
    Run $uv pip install --python $python --break-system-packages -r $requirements

    Say "Node $NodeMajor"
    $index = "https://nodejs.org/dist/latest-v$NodeMajor.x"
    $sums = (Invoke-WebRequest "$index/SHASUMS256.txt" -UseBasicParsing).Content
    if ($sums -notmatch "(?m)^([0-9a-f]{64})\s+(node-v[\d.]+-win-x64\.zip)\s*$") { throw "Could not find the Windows build of Node $NodeMajor at $index" }
    $nodeHash, $nodeName = $Matches[1], $Matches[2]
    $nodeZip = Join-Path $Tmp $nodeName
    Invoke-WebRequest "$index/$nodeName" -OutFile $nodeZip
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $nodeZip).Hash.ToLower() -ne $nodeHash) { throw "The Node download does not match its published checksum. Run the build again." }
    Expand-Archive -Force -LiteralPath $nodeZip -DestinationPath $Tmp
    Move-Item -LiteralPath (Join-Path $Tmp ($nodeName -replace "\.zip$", "")) -Destination (Join-Path $Runtime "node")

    Say "Checking the bundled runtime"
    $env:PYTHONPATH = $Repo
    try { Run $python -c "import anexis, fastapi, uvicorn, psutil, websockets, pyautogui, pyperclip, winpty, pygetwindow; print('python ok, anexis', anexis.__version__)" }
    finally { Remove-Item Env:PYTHONPATH }
    Run (Join-Path $Runtime "node\node.exe") --version
} elseif (-not (Test-Path (Join-Path $Runtime "python\python.exe"))) {
    throw "-SkipRuntime was given but there is no runtime from an earlier build. Run once without it."
}

Say "The app's own files"
if (Test-Path $Source) { Remove-Item -Recurse -Force -LiteralPath $Source }
New-Item -ItemType Directory -Force -Path $Source, (Join-Path $Source "desktop") | Out-Null
foreach ($folder in "anexis", "ui", "tools", "training", "profile") {
    # /XD and /XF leave out caches and anything personal that may sit in a working copy.
    robocopy (Join-Path $Repo $folder) (Join-Path $Source $folder) /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ /XF *.pyc about_me.yaml | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copying $folder failed (robocopy code $LASTEXITCODE)" }
}
$global:LASTEXITCODE = 0
foreach ($file in "pyproject.toml", "README.md", "anexis.toml.example", ".env.example") {
    Copy-Item -LiteralPath (Join-Path $Repo $file) -Destination $Source
}
foreach ($file in "frame.js", "preload.js", "seed.js") {
    Copy-Item -LiteralPath (Join-Path $Desktop $file) -Destination (Join-Path $Source "desktop")
}
Copy-Item -Recurse -LiteralPath (Join-Path $Desktop "assets") -Destination (Join-Path $Source "desktop\assets")

Say "The installer"
Push-Location $Desktop
try {
    Run npm install --no-audit --no-fund
    Run npm test
    Run npx electron-builder --win nsis --x64
} finally { Pop-Location }

$setup = Join-Path $Desktop "dist\AnexisSetup.exe"
if (-not (Test-Path $setup)) { throw "The build finished but $setup is missing." }
$size = [math]::Round((Get-Item $setup).Length / 1MB)
Say "Done: $setup ($size MB)"
Write-Host "Run it to install Anexis. It installs for your user only, no admin needed."
