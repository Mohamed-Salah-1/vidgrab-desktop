# Build VidGrab with PyInstaller.
#
# Two layouts:
#   .\build.ps1            -> single file  dist\VidGrab.exe      (portable, ~4-7s startup)
#   .\build.ps1 -Onedir    -> folder       dist\VidGrab\VidGrab.exe (fast startup)
#                             plus a shareable dist\VidGrab-windows-x64.zip
#
# A static FFmpeg (vendor\ffmpeg.exe) is embedded in both layouts so video+audio
# merging and MP3/M4A conversion work out of the box. At runtime the frozen app
# finds it via sys._MEIPASS (see downloader.find_ffmpeg); it also falls back to
# an ffmpeg.exe next to the EXE, then to PATH.

param(
    [switch]$Onedir
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
try {
    $python = Join-Path $here ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Virtual environment not found. Create it with: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller"
    }

    $hooks = Join-Path $here ".venv\Lib\site-packages\yt_dlp\__pyinstaller"

    $ffmpeg = Join-Path $here "vendor\ffmpeg.exe"
    if (-not (Test-Path $ffmpeg)) {
        throw "vendor\ffmpeg.exe not found. See README for how to obtain it."
    }

    $mode = if ($Onedir) { "--onedir" } else { "--onefile" }

    # Remove only this layout's prior output so a stale/running copy cannot
    # block the build, while keeping the other layout intact.
    if ($Onedir) {
        Remove-Item (Join-Path $here "dist\VidGrab") -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $here "dist\VidGrab-windows-x64.zip") -Force -ErrorAction SilentlyContinue
    } else {
        Remove-Item (Join-Path $here "dist\VidGrab.exe") -Force -ErrorAction SilentlyContinue
    }

    & $python -m PyInstaller `
        --noconfirm --clean $mode --windowed `
        --name VidGrab `
        --additional-hooks-dir $hooks `
        --collect-submodules yt_dlp `
        --collect-all curl_cffi `
        --collect-data certifi `
        --add-binary "$ffmpeg;." `
        main.py

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    Write-Host ""
    if ($Onedir) {
        $folder = Join-Path $here "dist\VidGrab"
        $exe = Join-Path $folder "VidGrab.exe"
        $zip = Join-Path $here "dist\VidGrab-windows-x64.zip"
        Compress-Archive -Path (Join-Path $folder "*") -DestinationPath $zip -Force
        Write-Host "Built folder:  $exe"
        Write-Host "Shareable zip: $zip"
    } else {
        Write-Host "Built: $here\dist\VidGrab.exe"
    }
}
finally {
    Pop-Location
}
