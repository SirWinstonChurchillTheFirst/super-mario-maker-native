# Baut die native Windows-Version dieses Spiels aus DEINEM EIGENEN Dump.
# Builds the native Windows version of this game from YOUR OWN game dump.
#
#   .\setup-windows.ps1 -GameDir "D:\Spiele\Mein Dump"                 (Ordner mit code, content, meta)
#   .\setup-windows.ps1 -GameDir "..." -SysDir "...\mlc01\sys"          (optional: Systemdateien DEINER Wii U)
#   .\setup-windows.ps1 -GameDir "..." -Jobs 6                          (weniger parallele Compiler-Jobs)
#
# Nothing from the game is downloaded or stored in this repository: the game's code is translated and compiled
# on your PC, into .\build; .\play\Start.bat starts it. Needs MSYS2 (installed with winget if missing).
param(
  [string]$GameDir,
  [string]$SysDir,
  [int]$Jobs = 0,
  [string]$Msys2 = $(if ($env:MSYS2_ROOT) { $env:MSYS2_ROOT } else { "C:\msys64" })
)
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$here = $PSScriptRoot
function Fail($de, $en) { Write-Host ""; Write-Host "FEHLER: $de" -ForegroundColor Red; Write-Host "ERROR:  $en" -ForegroundColor Red; exit 1 }
function Say($de, $en) { Write-Host $de; Write-Host "   $en" -ForegroundColor DarkGray }

$conf = @{}
foreach ($line in Get-Content "$here\game.conf") {
  if ($line -match '^\s*([A-Z_]+)=(.*)$') { $conf[$Matches[1]] = $Matches[2].Trim().Trim('"') }
}
$title = $conf["TITLE"]; $rpx = $conf["RPX"]
Say "== ${title}: native Windows-Version bauen ==" "== ${title}: building the native Windows version =="

# 1. Dein Spiel / your game
if (-not $GameDir) {
  Say "Wo liegt dein entpackter Dump von `"$title`" (Ordner mit code, content, meta)?" "Where is your unpacked dump (folder with code, content, meta)?"
  $GameDir = (Read-Host ">").Trim().Trim('"')
}
if (-not $GameDir -or -not (Test-Path -LiteralPath $GameDir -PathType Container)) { Fail "Spielordner nicht gefunden: $GameDir" "game folder not found: $GameDir" }
$GameDir = (Resolve-Path -LiteralPath $GameDir).Path.TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $GameDir "code\$rpx"))) {
  Fail "In $GameDir\code fehlt $rpx. Gebraucht wird DEIN eigener, entpackter Dump von `"$title`" (Ordner code, content, meta)." `
       "$GameDir\code has no $rpx. You need YOUR OWN unpacked dump of `"$title`" (folders code, content, meta)."
}
if ($SysDir) {
  if (-not (Test-Path -LiteralPath $SysDir -PathType Container)) { Fail "SysDir nicht gefunden: $SysDir" "SysDir not found: $SysDir" }
  $SysDir = (Resolve-Path -LiteralPath $SysDir).Path
}
if (-not [Environment]::Is64BitOperatingSystem) { Fail "Nur 64-Bit-Windows." "64-bit Windows only." }
try {
  Add-Type -Namespace Native -Name Cpu -MemberDefinition '[DllImport("kernel32.dll")] public static extern bool IsProcessorFeaturePresent(uint f);'
  if (-not [Native.Cpu]::IsProcessorFeaturePresent(40)) { Say "Warnung: dein Prozessor meldet kein AVX2 - das Programm braucht AVX2/FMA." "Warning: your CPU reports no AVX2 - the program needs AVX2/FMA." }
} catch {}
$free = (Get-PSDrive -Name ($here.Substring(0, 1))).Free / 1GB
$needGB = [double]$conf["DISK_GB"]
if ($needGB -and $free -lt $needGB) { Say "Warnung: auf dem Laufwerk sind nur $([int]$free) GB frei, gebraucht werden etwa $needGB GB." "Warning: only $([int]$free) GB free on this drive, about $needGB GB are needed." }

# 2. MSYS2 (Compiler clang, cmake, ninja, Python, git und die Bibliotheken) / MSYS2 with the build tools
$bash = Join-Path $Msys2 "usr\bin\bash.exe"
if (-not (Test-Path $bash)) {
  Say "MSYS2 fehlt - wird mit winget installiert ..." "MSYS2 is missing - installing it with winget ..."
  winget install --id MSYS2.MSYS2 -e --accept-package-agreements --accept-source-agreements
  if (-not (Test-Path $bash)) { Fail "MSYS2 ist nicht in $Msys2. Installiere es von https://www.msys2.org und starte dieses Skript nochmal (oder -Msys2 <Ordner>)." `
                                     "MSYS2 isn't in $Msys2. Install it from https://www.msys2.org and run this again (or pass -Msys2 <folder>)." }
}
$pkgs = "mingw-w64-clang-x86_64-clang mingw-w64-clang-x86_64-lld mingw-w64-clang-x86_64-cmake mingw-w64-clang-x86_64-ninja " +
        "mingw-w64-clang-x86_64-python mingw-w64-clang-x86_64-sdl3 mingw-w64-clang-x86_64-vulkan-headers mingw-w64-clang-x86_64-vulkan-loader " +
        "mingw-w64-clang-x86_64-shaderc mingw-w64-clang-x86_64-spirv-tools mingw-w64-clang-x86_64-zlib mingw-w64-clang-x86_64-zstd " +
        "mingw-w64-clang-x86_64-xz mingw-w64-clang-x86_64-ttf-dejavu git"
$env:MSYSTEM = "CLANG64"; $env:CHERE_INVOKING = "1"
Say "Pruefe/installiere die Bau-Pakete in MSYS2 (CLANG64) ..." "Checking/installing the build packages in MSYS2 (CLANG64) ..."
& $bash -lc "pacman -T $pkgs >/dev/null || pacman -S --needed --noconfirm $pkgs"
if ($LASTEXITCODE) {
  Fail "pacman konnte die Pakete nicht installieren. Bring MSYS2 auf den neuesten Stand (MSYS2-Fenster: pacman -Syu, ggf. zweimal) und starte nochmal." `
       "pacman could not install the packages. Update MSYS2 first (in an MSYS2 window: pacman -Syu, maybe twice) and run this again."
}

# 3. Uebersetzen + kompilieren (gemeinsam mit Linux: tools\native-build.sh) / translate + compile (shared with Linux)
#    Der Bau laeuft mit niedriger Prioritaet, damit der PC benutzbar bleibt. / Runs at low priority to keep the PC usable.
try { (Get-Process -Id $PID).PriorityClass = "BelowNormal" } catch {}
if ($SysDir) { $env:CAFE_SYS_DIR = $SysDir }
if ($Jobs -gt 0) { $env:JOBS = "$Jobs" }
$script = (Join-Path $here "tools\native-build.sh") -replace '\\', '/'
& $bash -l $script $GameDir
if ($LASTEXITCODE) { Fail "Der Bau ist fehlgeschlagen (Meldungen oben, Protokoll in build\build.log)." "The build failed (messages above, log in build\build.log)." }

if ($env:NATIVE_ONLY_TRANSLATE) { exit 0 }
Write-Host ""
Say "Fertig! Starten mit: $here\play\Start.bat" "Done! Start with: $here\play\Start.bat"
