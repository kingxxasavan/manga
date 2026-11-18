# Updates an installed Anexis from this repo, with no rebuild and no reinstall.
#
#     powershell -ExecutionPolicy Bypass -File update.ps1
#
# The installed app runs from a folder of plain files (the live copy). This
# script pulls the newest code and copies it over that folder. Anexis can stay
# open while it runs: the screen reloads and the brain restarts by themselves.
#
# You only need build.ps1 and the installer again when the bundled Python,
# Node or Python packages change, which is rare.
#
#   -NoPull   copy what is in this folder now, without asking git for newer code

param([switch]$NoPull)

$ErrorActionPreference = "Stop"
$Desktop = $PSScriptRoot
$Repo    = Split-Path $Desktop -Parent
$Data    = Join-Path $env:LOCALAPPDATA "Anexis"
$Live    = Join-Path $Data "app"

function Say($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

if (-not (Test-Path (Join-Path $Live "anexis"))) {
    throw "Anexis is not installed yet (nothing at $Live). Build and run the installer first: build.ps1"
}

if (-not $NoPull) {
    Say "Getting the newest code"
    $before = (Get-FileHash -LiteralPath $PSCommandPath).Hash
    git -C $Repo pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw "git pull failed. Fix that, or run again with -NoPull to use the code that is here." }
    # The pull may have brought a newer copy of this very script. PowerShell is
    # still running the old one, so hand over to the new one.
    if ((Get-FileHash -LiteralPath $PSCommandPath).Hash -ne $before) {
        Write-Host "This updater changed too. Running the new one."
        & powershell -ExecutionPolicy Bypass -File $PSCommandPath -NoPull
        exit $LASTEXITCODE
    }
}

Say "Keeping a copy of what is installed now"
$backup = Join-Path $Data ("app-backup-update-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
robocopy $Live $backup /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Could not make the backup (robocopy code $LASTEXITCODE). Nothing was changed." }
Write-Host "Backup: $backup"

Say "Copying the new files in"
# /E copies over what is there and adds what is new. It never deletes, so a
# file you or Claude added to the live copy stays where it is.
foreach ($folder in "anexis", "ui", "tools", "training", "profile") {
    robocopy (Join-Path $Repo $folder) (Join-Path $Live $folder) /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ /XF *.pyc about_me.yaml | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copying $folder failed (robocopy code $LASTEXITCODE). Your old files are in $backup" }
}
$global:LASTEXITCODE = 0
foreach ($file in "pyproject.toml", "README.md", "anexis.toml.example", ".env.example") {
    Copy-Item -Force -LiteralPath (Join-Path $Repo $file) -Destination $Live
}
New-Item -ItemType Directory -Force -Path (Join-Path $Live "desktop\assets") | Out-Null
foreach ($file in "frame.js", "preload.js", "seed.js") {
    Copy-Item -Force -LiteralPath (Join-Path $Desktop $file) -Destination (Join-Path $Live "desktop")
}
Copy-Item -Force -Path (Join-Path $Desktop "assets\*") -Destination (Join-Path $Live "desktop\assets")

Say "Done"
Write-Host "If Anexis is open it has already reloaded. Changes to the window itself (frame.js) show the next time you open it."
Write-Host "To go back: close Anexis, delete $Live, and rename $backup to app."
