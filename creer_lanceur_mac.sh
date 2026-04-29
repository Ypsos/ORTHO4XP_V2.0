#!/bin/bash
# ============================================================
#  ORTHO4XP V2 — Création du Lanceur Installation MAC
#  Génère Lanceur_Installation_Prerequis_MAC.app via Automator
#  À lancer UNE FOIS sur votre Mac depuis le dossier ORTHO4XP_V2
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Lanceur_Installation_Prerequis_MAC"
APP_PATH="$DIR/$APP_NAME.app"

echo "📍 Dossier ORTHO4XP_V2 : $DIR"
echo "🔨 Création de $APP_NAME.app ..."

# ── 1. Créer la structure du .app Automator ─────────────────
rm -rf "$APP_PATH"
mkdir -p "$APP_PATH/Contents/MacOS"
mkdir -p "$APP_PATH/Contents/Resources"

# ── 2. Copier le binaire Apple natif Automator ──────────────
STUB="/System/Library/CoreServices/Automator Application Stub.app/Contents/MacOS/Automator Application Stub"
if [ ! -f "$STUB" ]; then
    echo "❌ Automator Application Stub introuvable."
    echo "   Vérifiez que macOS est à jour."
    exit 1
fi
cp "$STUB" "$APP_PATH/Contents/MacOS/Application Stub"
echo "✅ Binaire Automator copié"

# ── 3. Créer Info.plist ──────────────────────────────────────
cat > "$APP_PATH/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>Application Stub</string>
    <key>CFBundleIdentifier</key><string>com.ypsos.ortho4xp.prerequis.mac</string>
    <key>CFBundleName</key><string>Lanceur_Installation_Prerequis_MAC</string>
    <key>CFBundleDisplayName</key><string>Lanceur Installation Prerequis MAC</string>
    <key>CFBundleVersion</key><string>2.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleSignature</key><string>????</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>com.apple.security.app-sandbox</key><false/>
</dict>
</plist>
PLIST
echo "✅ Info.plist créé"

# ── 4. Créer le workflow Automator (.wflow) ──────────────────
# Le script détecte son propre dossier et lance INSTALL_PREREQUIS.py
SCRIPT='SCRIPT_DIR="$(dirname "$( cd "$(dirname "$0")"; cd ..; cd ..; pwd )")"\ncd "$SCRIPT_DIR"\nif [ -f "$SCRIPT_DIR/INSTALL_PREREQUIS.py" ]; then\n    /usr/bin/python3 "$SCRIPT_DIR/INSTALL_PREREQUIS.py"\nelse\n    osascript -e "display dialog \"INSTALL_PREREQUIS.py introuvable dans :\\n$SCRIPT_DIR\\n\\nVérifiez que l archive est bien décompressée.\" buttons {\"OK\"} with title \"Ortho4XP — Erreur\" with icon stop"\nfi'

cat > "$APP_PATH/Contents/document.wflow" << WFLOW
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>AMApplicationBuild</key><string>521</string>
    <key>AMApplicationVersion</key><string>2.10</string>
    <key>AMDocumentVersion</key><string>2</string>
    <key>actions</key>
    <array>
        <dict>
            <key>action</key>
            <dict>
                <key>AMAccepts</key>
                <dict>
                    <key>Container</key><string>List</string>
                    <key>Optional</key><true/>
                    <key>Types</key><array><string>com.apple.cocoa.string</string></array>
                </dict>
                <key>AMActionVersion</key><string>2.0.3</string>
                <key>AMApplication</key><array><string>Automator</string></array>
                <key>AMParameterProperties</key>
                <dict>
                    <key>COMMAND_STRING</key><dict/>
                    <key>CheckedForUserDefaultShell</key><dict/>
                    <key>inputMethod</key><dict/>
                    <key>shell</key><dict/>
                    <key>source</key><dict/>
                </dict>
                <key>AMProvides</key>
                <dict>
                    <key>Container</key><string>List</string>
                    <key>Types</key><array><string>com.apple.cocoa.string</string></array>
                </dict>
                <key>ActionBundlePath</key>
                <string>/System/Library/Automator/Run Shell Script.action</string>
                <key>ActionName</key><string>Run Shell Script</string>
                <key>ActionParameters</key>
                <dict>
                    <key>COMMAND_STRING</key>
                    <string>APP_PATH="\$(dirname "\$(dirname "\$AUTOMATOR_WORKFLOW_PATH")")"
SCRIPT_DIR="\$(dirname "\$APP_PATH")"
cd "\$SCRIPT_DIR"
if [ -f "\$SCRIPT_DIR/INSTALL_PREREQUIS.py" ]; then
    /usr/bin/python3 "\$SCRIPT_DIR/INSTALL_PREREQUIS.py"
else
    osascript -e "display dialog \"INSTALL_PREREQUIS.py introuvable dans :\\n\$SCRIPT_DIR\\n\\nVerifiez que l archive est bien decompressee.\" buttons {\"OK\"} with title \"Ortho4XP Erreur\" with icon stop"
fi</string>
                    <key>CheckedForUserDefaultShell</key><true/>
                    <key>inputMethod</key><integer>0</integer>
                    <key>shell</key><string>/bin/bash</string>
                    <key>source</key><string></string>
                </dict>
            </dict>
        </dict>
    </array>
    <key>workflowMetaData</key>
    <dict>
        <key>workflowTypeIdentifier</key>
        <string>com.apple.automator.application</string>
    </dict>
</dict>
</plist>
WFLOW
echo "✅ Workflow Automator créé"

# ── 5. Permissions correctes ─────────────────────────────────
chmod +x "$APP_PATH/Contents/MacOS/Application Stub"
xattr -cr "$APP_PATH"
echo "✅ Permissions appliquées"

# ── 6. Signature ad-hoc ──────────────────────────────────────
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null
echo "✅ Signature ad-hoc appliquée"

echo ""
echo "✅ $APP_NAME.app créé dans :"
echo "   $APP_PATH"
echo ""
echo "📌 Transférez ce .app sur GitHub avec GitHub Desktop."
echo "   Les permissions sont préservées car créé localement."
