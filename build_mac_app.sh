#!/usr/bin/env bash
# build_mac_app.sh — Crée Ortho4XP.app et Ortho4XP.dmg pour macOS
# Prérequis : Python 3.12 avec tkinter, py2app  OU  PyInstaller
# Usage : bash build_mac_app.sh [--dmg]
set -euo pipefail

APP_NAME="Ortho4XP"
BUNDLE_ID="org.ortho4xp.launcher"
PYTHON="${PYTHON:-python3.12}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_NAME.app"

# ── Couleurs ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "${CYAN}==> $1${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
err()  { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

# ── Vérifie Python ────────────────────────────────────────────────────────
step "Vérification de Python…"
if ! command -v "$PYTHON" &>/dev/null; then
    err "Python introuvable : $PYTHON\n  Installez-le avec : brew install python@3.12"
fi
PY_VER=$("$PYTHON" --version 2>&1)
ok "$PY_VER ($PYTHON)"

# ── Installe PyInstaller si absent ────────────────────────────────────────
step "Vérification de PyInstaller…"
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "  Installation de PyInstaller…"
    "$PYTHON" -m pip install pyinstaller --quiet
fi
ok "PyInstaller disponible"

# ── Icône (génère une icône minimale si absente) ──────────────────────────
ICON_SRC="$SCRIPT_DIR/icon.icns"
if [ ! -f "$ICON_SRC" ]; then
    step "Génération d'une icône par défaut…"
    # Crée un iconset minimal 1024×1024 via Python + Pillow
    "$PYTHON" - <<'PYEOF'
from PIL import Image, ImageDraw, ImageFont
import os, subprocess, shutil, tempfile

sizes = [16,32,64,128,256,512,1024]
iconset = tempfile.mkdtemp(suffix=".iconset")

for s in sizes:
    img = Image.new("RGBA", (s,s), (0,0,0,0))
    d = ImageDraw.Draw(img)
    # Fond dégradé bleu
    for y in range(s):
        r = int(30 + (y/s)*40)
        g = int(60 + (y/s)*80)
        b = int(200 - (y/s)*40)
        d.line([(0,y),(s,y)], fill=(r,g,b,255))
    # Avion
    cx,cy = s//2, s//2
    sz = s//3
    d.polygon([(cx,cy-sz),(cx+sz//2,cy+sz//2),(cx,cy+sz//4),(cx-sz//2,cy+sz//2)],
              fill=(255,255,255,230))
    img.save(f"{iconset}/icon_{s}x{s}.png")
    if s <= 512:
        img2 = img.resize((s*2,s*2), Image.LANCZOS)
        img2.save(f"{iconset}/icon_{s}x{s}@2x.png")

# Convertit en .icns avec iconutil (macOS uniquement)
try:
    subprocess.run(["iconutil","-c","icns",iconset,"-o","icon.icns"], check=True)
except Exception as e:
    print(f"  iconutil non disponible ({e}), icône ignorée.")
finally:
    shutil.rmtree(iconset, ignore_errors=True)
PYEOF
fi

# ── Construction avec PyInstaller ─────────────────────────────────────────
step "Construction de l'app bundle avec PyInstaller…"
mkdir -p "$DIST_DIR"

ICON_FLAG=""
[ -f "$ICON_SRC" ] && ICON_FLAG="--icon=$ICON_SRC"

"$PYTHON" -m PyInstaller \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    --distpath "$DIST_DIR" \
    --workpath "$SCRIPT_DIR/build" \
    --specpath "$SCRIPT_DIR/build" \
    $ICON_FLAG \
    --add-data "Ortho4XP.py:." \
    --add-data "Ortho4XP.cfg:." \
    --add-data "requirements.txt:." \
    --hidden-import "tkinter" \
    --hidden-import "tkinter.ttk" \
    --hidden-import "tkinter.scrolledtext" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    "$SCRIPT_DIR/Ortho4XP_Launcher.py" \
    --noconfirm

ok "App bundle créé : $APP_BUNDLE"

# ── Patch Info.plist ──────────────────────────────────────────────────────
PLIST="$APP_BUNDLE/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    step "Personnalisation de Info.plist…"
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Ortho4XP"      "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 1.40"   "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :NSHighResolutionCapable true"      "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion 12.0"       "$PLIST" 2>/dev/null || true
    ok "Info.plist mis à jour"
fi

# ── Génération du DMG (optionnel) ─────────────────────────────────────────
if [[ "${1:-}" == "--dmg" ]]; then
    step "Création du fichier DMG…"
    DMG_OUT="$DIST_DIR/${APP_NAME}_Installer.dmg"
    DMG_TMP="$DIST_DIR/dmg_tmp"
    mkdir -p "$DMG_TMP"
    cp -r "$APP_BUNDLE" "$DMG_TMP/"
    # Lien Applications pour drag & drop
    ln -sf /Applications "$DMG_TMP/Applications"

    hdiutil create \
        -volname "$APP_NAME" \
        -srcfolder "$DMG_TMP" \
        -ov \
        -format UDZO \
        "$DMG_OUT"

    rm -rf "$DMG_TMP"
    ok "DMG créé : $DMG_OUT"
    echo ""
    echo "  ➜ Distribuez $DMG_OUT"
    echo "    L'utilisateur glisse Ortho4XP.app dans Applications, puis double-clique."
fi

echo ""
echo -e "${GREEN}✅  Build terminé !${NC}"
echo "  App : $APP_BUNDLE"
echo ""
echo "  Commandes :"
echo "    Ouvrir l'app  : open \"$APP_BUNDLE\""
echo "    Créer le DMG  : bash build_mac_app.sh --dmg"
