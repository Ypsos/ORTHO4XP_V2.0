# build_windows_exe.ps1
# Construit Ortho4XP_Launcher.exe (PyInstaller) + installeur Setup.exe (NSIS optionnel)
# Usage : powershell -ExecutionPolicy Bypass -File build_windows_exe.ps1 [-nsis]
param([switch]$nsis)

$ErrorActionPreference = "Stop"
$APP_NAME    = "Ortho4XP"
$VERSION     = "1.40"
$SCRIPT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path
$DIST_DIR    = Join-Path $SCRIPT_DIR "dist"
$EXE_OUT     = Join-Path $DIST_DIR "$APP_NAME\$APP_NAME.exe"

function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-OK($m)   { Write-Host "  [OK] $m"    -ForegroundColor Green }
function Write-Err($m)  { Write-Host "  [!!] $m"    -ForegroundColor Red; exit 1 }

# ── Python ────────────────────────────────────────────────────────────────
Write-Step "Détection de Python…"
$python = $null
foreach ($c in @("python","python3")) {
    try {
        $v = & $c --version 2>&1
        if ($v -match "3\.[1-9][0-9]") { $python = $c; break }
    } catch {}
}
if (-not $python) { Write-Err "Python 3.10+ introuvable dans le PATH." }
Write-OK "$python : $(& $python --version 2>&1)"

# ── PyInstaller ───────────────────────────────────────────────────────────
Write-Step "Vérification de PyInstaller…"
$piCheck = & $python -c "import PyInstaller" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installation de PyInstaller…"
    & $python -m pip install pyinstaller --quiet
}
Write-OK "PyInstaller disponible"

# ── Build EXE ─────────────────────────────────────────────────────────────
Write-Step "Construction de l'exécutable Windows…"
New-Item -ItemType Directory -Force -Path $DIST_DIR | Out-Null

$args_pi = @(
    "-m", "PyInstaller",
    "--name", $APP_NAME,
    "--windowed",                        # pas de console noire
    "--onedir",                          # dossier (plus rapide au démarrage)
    "--distpath", $DIST_DIR,
    "--workpath", (Join-Path $SCRIPT_DIR "build"),
    "--specpath", (Join-Path $SCRIPT_DIR "build"),
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.ttk",
    "--hidden-import", "tkinter.scrolledtext",
    "--add-data", "Ortho4XP.py;.",
    "--add-data", "Ortho4XP.cfg;.",
    "--add-data", "requirements.txt;.",
    "--noconfirm"
)

# Icône optionnelle
$iconPath = Join-Path $SCRIPT_DIR "icon.ico"
if (Test-Path $iconPath) { $args_pi += "--icon=$iconPath" }

$args_pi += (Join-Path $SCRIPT_DIR "Ortho4XP_Launcher.py")

& $python @args_pi
if ($LASTEXITCODE -ne 0) { Write-Err "PyInstaller a échoué." }
Write-OK "Exécutable créé : $EXE_OUT"

# ── Copie des fichiers Ortho4XP dans le dossier dist ─────────────────────
Write-Step "Copie des fichiers Ortho4XP…"
$ortho_dist = Join-Path $DIST_DIR $APP_NAME
foreach ($f in @("Ortho4XP.py","Ortho4XP.cfg","requirements.txt","src","Utils")) {
    $src = Join-Path $SCRIPT_DIR $f
    if (Test-Path $src) {
        Copy-Item -Recurse -Force $src $ortho_dist
        Write-Host "  Copié : $f"
    }
}
Write-OK "Fichiers copiés"

# ── Raccourci Bureau (optionnel) ──────────────────────────────────────────
Write-Step "Création du raccourci Bureau…"
try {
    $WS        = New-Object -ComObject WScript.Shell
    $shortcut  = $WS.CreateShortcut(
        [System.IO.Path]::Combine(
            [System.Environment]::GetFolderPath("Desktop"),
            "$APP_NAME.lnk"
        )
    )
    $shortcut.TargetPath       = $EXE_OUT
    $shortcut.WorkingDirectory = $ortho_dist
    $shortcut.Description      = "Ortho4XP – Générateur de scènes X-Plane"
    $shortcut.Save()
    Write-OK "Raccourci créé sur le Bureau"
} catch {
    Write-Host "  (raccourci ignoré : $_)" -ForegroundColor Yellow
}

# ── Script NSIS (installeur Setup.exe) ────────────────────────────────────
if ($nsis) {
    Write-Step "Génération du script NSIS…"
    $nsisScript = Join-Path $SCRIPT_DIR "build\installer.nsi"
    $nsisContent = @"
!define APP_NAME    "$APP_NAME"
!define VERSION     "$VERSION"
!define PUBLISHER   "Ortho4XP Community"
!define EXE_NAME    "$APP_NAME.exe"
!define DIST_DIR    "$ortho_dist"

Name "\${APP_NAME} \${VERSION}"
OutFile "$DIST_DIR\${APP_NAME}_Setup.exe"
InstallDir "\$PROGRAMFILES64\Ortho4XP"
InstallDirRegKey HKCU "Software\Ortho4XP" "Install_Dir"
RequestExecutionLevel user

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Ortho4XP (requis)" SecMain
  SectionIn RO
  SetOutPath "\$INSTDIR"
  File /r "\${DIST_DIR}\*.*"

  ; Raccourci Bureau
  CreateShortcut "\$DESKTOP\\Ortho4XP.lnk" "\$INSTDIR\\\${EXE_NAME}" "" "\$INSTDIR\\\${EXE_NAME}" 0

  ; Raccourci Menu Démarrer
  CreateDirectory "\$SMPROGRAMS\\Ortho4XP"
  CreateShortcut  "\$SMPROGRAMS\\Ortho4XP\\Ortho4XP.lnk" "\$INSTDIR\\\${EXE_NAME}"
  CreateShortcut  "\$SMPROGRAMS\\Ortho4XP\\Désinstaller.lnk" "\$INSTDIR\\Uninstall.exe"

  ; Désinstalleur
  WriteUninstaller "\$INSTDIR\\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\\Ortho4XP" \
              "DisplayName" "Ortho4XP \${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\\Ortho4XP" \
              "UninstallString" '"\$INSTDIR\\Uninstall.exe"'
SectionEnd

Section "Uninstall"
  Delete "\$INSTDIR\\Uninstall.exe"
  RMDir  /r "\$INSTDIR"
  Delete "\$DESKTOP\\Ortho4XP.lnk"
  RMDir  /r "\$SMPROGRAMS\\Ortho4XP"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Ortho4XP"
SectionEnd
"@
    $nsisContent | Out-File -Encoding UTF8 $nsisScript

    # Compile avec NSIS si installé
    $makensis = $null
    foreach ($p in @("C:\Program Files (x86)\NSIS\makensis.exe","C:\Program Files\NSIS\makensis.exe")) {
        if (Test-Path $p) { $makensis = $p; break }
    }
    if ($makensis) {
        & $makensis $nsisScript
        Write-OK "Setup.exe créé dans $DIST_DIR"
    } else {
        Write-Host "  NSIS non installé. Script généré : $nsisScript" -ForegroundColor Yellow
        Write-Host "  Installez NSIS (https://nsis.sourceforge.io) puis :" -ForegroundColor Yellow
        Write-Host "    makensis `"$nsisScript`"" -ForegroundColor White
    }
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  Build terminé !" -ForegroundColor Green
Write-Host "  EXE  : $EXE_OUT" -ForegroundColor White
Write-Host ""
Write-Host "  Pour créer un installeur Setup.exe :" -ForegroundColor Cyan
Write-Host "    .\build_windows_exe.ps1 -nsis" -ForegroundColor White
Write-Host "=====================================================" -ForegroundColor Green
