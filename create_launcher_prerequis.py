#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_launcher.py — Ortho4XP V2.0
Génère le lanceur natif par plateforme :
  macOS   → Lanceur_Installation_Prerequis.app  (binaire C autonome, zéro dépendance)
  Windows → Lanceur_Installation_Prerequis.vbs
  Linux   → Lanceur_Installation_Prerequis.desktop + .sh
"""
from __future__ import annotations
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path

HERE   = Path(__file__).resolve().parent
SYSTEM = platform.system()

if SYSTEM == "Windows":
    VENV_PY = HERE / "venv" / "Scripts" / "python.exe"
else:
    VENV_PY = HERE / "venv" / "bin" / "python3"


# ══════════════════════════════════════════════════════════════════════════════
#  macOS — INSTALL_ORTHO4XP.app  (binaire C universel autonome)
# ══════════════════════════════════════════════════════════════════════════════
#
#  Flux complet géré par le binaire C (zéro Python requis au départ) :
#
#  1. Trouve ORTHO4XP_V2/ via _NSGetExecutablePath (chemin relatif)
#  2. Vérifie Python 3.12 → absent → installe Homebrew + python@3.12
#     via osascript dialogs natifs macOS (aucun terminal visible)
#  3. Vérifie venv/ → absent → le crée silencieusement
#  4. Lance INSTALL_PREREQUIS.py → fenêtre verte tkinter prend le relais
#
# ══════════════════════════════════════════════════════════════════════════════

LAUNCHER_C_SOURCE = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <libgen.h>
#include <stdint.h>
#include <sys/stat.h>
#include <sys/wait.h>

extern int _NSGetExecutablePath(char *buf, uint32_t *bufsize);

static int path_exists(const char *p) {
    struct stat st; return stat(p, &st) == 0;
}

/* Dialog bloquant natif */
static void dialog(const char *title, const char *msg, const char *icon) {
    char script[4096];
    snprintf(script, sizeof(script),
        "display dialog \"%s\" buttons {\"OK\"} "
        "default button \"OK\" with title \"%s\" with icon %s",
        msg, title, icon);
    char *args[] = { "/usr/bin/osascript", "-e", script, NULL };
    pid_t pid = fork();
    if (pid == 0) { execv("/usr/bin/osascript", args); _exit(1); }
    if (pid > 0) { int st; waitpid(pid, &st, 0); }
}

/* Notification non-bloquante */
static void notify(const char *title, const char *msg) {
    char script[2048];
    snprintf(script, sizeof(script),
        "display notification \"%s\" "
        "with title \"%s\" subtitle \"Ortho4XP V2.0\"",
        msg, title);
    char *args[] = { "/usr/bin/osascript", "-e", script, NULL };
    pid_t pid = fork();
    if (pid == 0) { execv("/usr/bin/osascript", args); _exit(1); }
    if (pid > 0) { int st; waitpid(pid, &st, 0); }
}

/* Exécute cmd[] via fork/execv et attend la fin — pas de bash, pas de PATH */
static int run_direct(const char *argv0, char *const argv[], const char *log) {
    pid_t pid = fork();
    if (pid == 0) {
        /* Enfant : rediriger stdout+stderr vers le log */
        FILE *f = fopen(log, "a");
        if (f) {
            int fd = fileno(f);
            dup2(fd, STDOUT_FILENO);
            dup2(fd, STDERR_FILENO);
        }
        execv(argv0, argv);
        _exit(1);
    } else if (pid > 0) {
        int status;
        waitpid(pid, &status, 0);
        return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
    }
    return 1;
}

/* Installe Homebrew via curl+bash — seule exception qui nécessite un shell */
static int install_homebrew(const char *log) {
    char *argv[] = {
        "/bin/bash", "-c",
        "NONINTERACTIVE=1 /bin/bash -c "
        "\"$(/usr/bin/curl -fsSL "
        "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"",
        NULL
    };
    return run_direct("/bin/bash", argv, log);
}

static int find_python312(char *out, size_t n) {
    const char *c[] = {
        "/opt/homebrew/opt/python@3.12/bin/python3.12",
        "/usr/local/opt/python@3.12/bin/python3.12",
        "/opt/homebrew/opt/python@3.12/libexec/bin/python3.12",
        "/opt/homebrew/Cellar/python@3.12/3.12.13/bin/python3.12",
        "/opt/homebrew/Cellar/python@3.12/3.12.13_1/bin/python3.12",
        "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.12",
        NULL
    };
    for (int i = 0; c[i]; i++) {
        if (path_exists(c[i])) {
            strncpy(out, c[i], n-1); out[n-1]='\0'; return 1;
        }
    }
    return 0;
}

static int find_brew(char *out, size_t n) {
    const char *c[] = {
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
        NULL
    };
    for (int i = 0; c[i]; i++) {
        if (path_exists(c[i])) {
            strncpy(out, c[i], n-1); out[n-1]='\0'; return 1;
        }
    }
    return 0;
}

int main(int argc, char **argv) {

    /* 0. Auto-suppression quarantaine */
    {
        char exe_q[PATH_MAX]; uint32_t sz_q = sizeof(exe_q);
        if (_NSGetExecutablePath(exe_q, &sz_q) == 0) {
            char t1[PATH_MAX], t2[PATH_MAX], t3[PATH_MAX], app_q[PATH_MAX];
            strncpy(t1, exe_q,       PATH_MAX-1);
            strncpy(t2, dirname(t1), PATH_MAX-1);
            strncpy(t3, dirname(t2), PATH_MAX-1);
            strncpy(app_q, dirname(t3), PATH_MAX-1);
            char *xa[] = { "/usr/bin/xattr", "-cr", app_q, NULL };
            run_direct("/usr/bin/xattr", xa, "/dev/null");
        }
    }

    /* 1. Trouver ROOT_DIR */
    char exe[PATH_MAX]; uint32_t sz = sizeof(exe);
    if (_NSGetExecutablePath(exe, &sz) != 0) {
        dialog("Ortho4XP — Erreur",
            "Impossible de localiser le dossier Ortho4XP.", "caution");
        return 1;
    }
    char real[PATH_MAX];
    if (!realpath(exe, real)) strncpy(real, exe, PATH_MAX-1);

    char t1[PATH_MAX], t2[PATH_MAX], t3[PATH_MAX], root[PATH_MAX];
    strncpy(t1, real,         PATH_MAX-1);
    strncpy(t2, dirname(t1),  PATH_MAX-1);
    strncpy(t3, dirname(t2),  PATH_MAX-1);
    char tmp[PATH_MAX];
    strncpy(tmp, dirname(t3), PATH_MAX-1);
    strncpy(root, dirname(tmp), PATH_MAX-1);

    chdir(root);

    char log[PATH_MAX], bootstrap[PATH_MAX], venv_py[PATH_MAX], venv_dir[PATH_MAX];
    snprintf(log,       sizeof(log),       "%s/ortho4xp_install.log", root);
    snprintf(bootstrap, sizeof(bootstrap), "%s/INSTALL_PREREQUIS.py",    root);
    snprintf(venv_py,   sizeof(venv_py),   "%s/venv/bin/python3",     root);
    snprintf(venv_dir,  sizeof(venv_dir),  "%s/venv",                 root);

    /* 2. Vérifier INSTALL_PREREQUIS.py */
    if (!path_exists(bootstrap)) {
        char msg[512];
        snprintf(msg, sizeof(msg),
            "INSTALL_PREREQUIS.py introuvable dans :\\n%s\\n\\n"
            "Verifiez que l'archive est bien decompressee.", root);
        dialog("Ortho4XP — Fichier manquant", msg, "stop");
        return 1;
    }

    /* 3. Chercher Python 3.12 */
    char py312[PATH_MAX] = {0};
    int has_py = find_python312(py312, sizeof(py312));

    /* Toujours passer par INSTALL_PREREQUIS.py — jamais directement le Launcher */
    /* INSTALL_PREREQUIS.py gère lui-même le cas "tout déjà OK" */

    /* 4. Python absent → installer Homebrew + Python */
    if (!has_py) {
        dialog("Ortho4XP V2.0 — Installation requise",
            "Python 3.12 n'est pas installe sur ce Mac.\\n\\n"
            "L'installation va demarrer automatiquement :\\n"
            "  - Homebrew\\n"
            "  - Python 3.12\\n\\n"
            "Duree estimee : 5 a 15 minutes.\\n"
            "Cliquez OK pour demarrer.", "note");

        char brew[PATH_MAX] = {0};
        if (!find_brew(brew, sizeof(brew))) {
            notify("Etape 1/3", "Installation de Homebrew...");
            install_homebrew(log);
            if (!find_brew(brew, sizeof(brew))) {
                dialog("Ortho4XP — Erreur Homebrew",
                    "Homebrew n'a pas pu etre installe.\\n\\n"
                    "Ouvrez Safari : https://brew.sh\\n"
                    "Puis relancez.", "stop");
                return 1;
            }
        }

        notify("Etape 2/3", "Installation de Python 3.12...");
        char *brew_args[] = { brew, "install", "python@3.12", "python-tk@3.12", NULL };
        run_direct(brew, brew_args, log);

        has_py = find_python312(py312, sizeof(py312));
        if (!has_py) {
            dialog("Ortho4XP — Erreur Python",
                "Python 3.12 n'a pas pu etre installe.\\n\\n"
                "Ouvrez le Terminal et tapez :\\n"
                "brew install python@3.12 python-tk@3.12", "stop");
            return 1;
        }
        notify("Etape 3/3", "Python 3.12 installe avec succes !");
    }

    /* 5. Créer venv si absent — appel direct sans bash */
    if (!path_exists(venv_dir)) {
        notify("Preparation", "Creation de l'environnement Python...");
        char *venv_args[] = { py312, "-m", "venv", venv_dir, NULL };
        run_direct(py312, venv_args, log);
    }

    /* 6. Lancer via script shell — évite que macOS ouvre l'Éditeur de Script */
    notify("Lancement", "Ouverture du Launcher Ortho4XP...");
    char sh_path[PATH_MAX];
    snprintf(sh_path, sizeof(sh_path), "%s/_ortho_launch.sh", root);
    FILE *sh = fopen(sh_path, "w");
    if (sh) {
        fprintf(sh, "#!/bin/sh\n");
        fprintf(sh, "exec \"%s\" \"%s\"\n", py312, bootstrap);
        fclose(sh);
        chmod(sh_path, 0755);
    }
    char *sh_args[] = { "/bin/sh", sh_path, NULL };
    run_direct("/bin/sh", sh_args, log);
    return 0;
}

"""

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundleIdentifier</key><string>com.ypsos.ortho4xp.prerequis</string>
    <key>CFBundleName</key><string>Lanceur Installation Prerequis</string>
    <key>CFBundleDisplayName</key><string>Lanceur Installation Prerequis</string>
    <key>CFBundleVersion</key><string>2.0</string>
    <key>CFBundleShortVersionString</key><string>2.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSRequiresAquaSystemAppearance</key><false/>
    <key>LSUIElement</key><false/>
</dict>
</plist>
"""

VBS_SCRIPT = r"""
' Lanceur_Installation_Prerequis.vbs — Ortho4XP V2.0
' Lance INSTALL_PREREQUIS.py sans console noire
' Installe Python 3.12 via winget si absent

Option Explicit

Dim WshShell, fso, scriptDir, bootstrap, python
Set WshShell = CreateObject("WScript.Shell")
Set fso      = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
bootstrap = scriptDir & "\INSTALL_PREREQUIS.py"

If Not fso.FileExists(bootstrap) Then
    MsgBox "INSTALL_PREREQUIS.py introuvable dans :" & vbCrLf & scriptDir & vbCrLf & vbCrLf & _
           "Vérifiez que l'archive est bien décompressée.", _
           vbCritical, "Ortho4XP — Fichier manquant"
    WScript.Quit
End If

python = ""
Dim pyPaths(5)
pyPaths(0) = "C:\Python312\python.exe"
pyPaths(1) = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\python.exe"
pyPaths(2) = WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
pyPaths(3) = scriptDir & "\venv\Scripts\pythonw.exe"
pyPaths(4) = scriptDir & "\venv\Scripts\python.exe"
pyPaths(5) = "C:\Program Files\Python312\python.exe"

Dim i
For i = 0 To 5
    If fso.FileExists(pyPaths(i)) Then
        python = pyPaths(i)
        Exit For
    End If
Next

If python = "" Then
    Dim answer
    answer = MsgBox("Python 3.12 n'est pas installe." & vbCrLf & vbCrLf & _
        "L'installation va demarrer automatiquement." & vbCrLf & _
        "Duree estimee : 2 a 5 minutes." & vbCrLf & vbCrLf & _
        "Cliquez OK pour continuer.", _
        vbOKCancel + vbInformation, "Ortho4XP V2.0 — Installation Python")

    If answer <> vbOK Then WScript.Quit

    WshShell.Run "winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements", 1, True

    For i = 0 To 5
        If fso.FileExists(pyPaths(i)) Then
            python = pyPaths(i)
            Exit For
        End If
    Next

    If python = "" Then
        MsgBox "Installation automatique impossible." & vbCrLf & vbCrLf & _
            "La page de telechargement va s'ouvrir." & vbCrLf & _
            "Installez Python 3.12 puis relancez." & vbCrLf & vbCrLf & _
            "IMPORTANT : Cochez 'Add Python to PATH' !", _
            vbExclamation, "Ortho4XP — Python manquant"
        WshShell.Run "https://www.python.org/downloads/release/python-3120/"
        WScript.Quit
    End If

    MsgBox "Python 3.12 installe avec succes !", vbInformation, "Ortho4XP"
End If

Dim pyExe
pyExe = python
Dim pyW
pyW = Replace(python, "python.exe", "pythonw.exe")
If fso.FileExists(pyW) Then pyExe = pyW

WshShell.Run Chr(34) & pyExe & Chr(34) & " " & Chr(34) & bootstrap & Chr(34), 1, False
"""


def create_mac_app():
    """Crée Lanceur_Installation_Prerequis.app avec binaire C autonome."""
    import shutil

    app_path  = HERE / "Lanceur_Installation_Prerequis.app"
    contents  = app_path / "Contents"
    macos_dir = contents / "MacOS"
    res_dir   = contents / "Resources"

    if app_path.exists():
        shutil.rmtree(str(app_path))
        print("  ♻️  Ancien .app supprimé.")

    macos_dir.mkdir(parents=True)
    res_dir.mkdir(parents=True)

    (contents / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")

    # Icône avec Pillow (non bloquant)
    try:
        from PIL import Image, ImageDraw
        iconset = res_dir / "AppIcon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in [16, 32, 64, 128, 256, 512]:
            img = Image.new("RGBA", (s, s), (59, 91, 73, 255))
            d = ImageDraw.Draw(img)
            m = s // 8
            d.ellipse([m, m, s - m, s - m], fill=(42, 66, 53, 255))
            cx, cy, sz = s // 2, s // 2, s // 3
            d.polygon(
                [(cx, cy - sz), (cx + sz // 2, cy + sz // 2),
                 (cx, cy + sz // 4), (cx - sz // 2, cy + sz // 2)],
                fill=(166, 227, 161, 230)
            )
            img.save(iconset / f"icon_{s}x{s}.png")
            if s <= 256:
                img.resize((s * 2, s * 2), Image.LANCZOS).save(
                    iconset / f"icon_{s}x{s}@2x.png")
        r = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(res_dir / "AppIcon.icns")],
            capture_output=True)
        if r.returncode == 0:
            print("  ✅ Icône .icns générée.")
        shutil.rmtree(str(iconset))
    except Exception as e:
        print(f"  ℹ️  Icône non générée ({e}) — non bloquant.")

    # Compilation binaire C
    c_file  = HERE / "_launcher_tmp.c"
    exe_out = macos_dir / "launch"
    c_file.write_text(LAUNCHER_C_SOURCE, encoding="utf-8")

    print("  🔨 Compilation du binaire C...")
    compiled = False
    for arch_flags in [["-arch", "arm64", "-arch", "x86_64"], []]:
        cmd = ["gcc"] + arch_flags + [
            str(c_file), "-o", str(exe_out),
            "-framework", "Foundation", "-O2"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            label = "universel arm64+x86_64" if arch_flags else "natif"
            print(f"  ✅ Binaire compilé ({label}).")
            compiled = True
            break
        else:
            print(f"  ⚠️  {arch_flags or 'natif'}: {r.stderr.strip()[:100]}")

    c_file.unlink(missing_ok=True)

    if not compiled:
        print("  ⚠️  gcc indisponible — fallback shell script.")
        _create_shell_fallback(exe_out)
    else:
        exe_out.chmod(exe_out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Supprimer quarantaine + signer
    try:
        subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True, timeout=10)
        print("  ✅ Quarantaine supprimée.")
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app_path)],
            capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            print("  ✅ Signature ad-hoc appliquée.")
    except Exception:
        pass

    print(f"\n  ✅ App créée : {app_path.name}")
    print("  Si macOS bloque : clic droit → Ouvrir → Ouvrir quand même")
    return app_path


def _create_shell_fallback(exe_out: Path):
    """Shell script fallback si gcc absent — même logique que le binaire C."""
    script = r"""#!/bin/bash
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENTS_DIR="$(dirname "$MACOS_DIR")"
APP_DIR="$(dirname "$CONTENTS_DIR")"
ROOT_DIR="$(dirname "$APP_DIR")"
cd "$ROOT_DIR" || exit 1

LOG="$ROOT_DIR/ortho4xp_install.log"
BOOTSTRAP="$ROOT_DIR/INSTALL_PREREQUIS.py"
VENV_PY="$ROOT_DIR/venv/bin/python3"

echo "=== $(date) ===" >> "$LOG"

[ ! -f "$BOOTSTRAP" ] && {
    osascript -e "display dialog \"INSTALL_PREREQUIS.py introuvable dans :\n$ROOT_DIR\" buttons {\"OK\"} default button \"OK\" with title \"Ortho4XP — Fichier manquant\" with icon stop"
    exit 1
}

find_py312() {
    for p in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
              /opt/homebrew/opt/python@3.12/bin/python3.12; do
        [ -f "$p" ] && echo "$p" && return 0
    done; return 1
}

PY312=$(find_py312)

[ -n "$PY312" ] && [ -f "$VENV_PY" ] && {
    PYTHONPATH="$ROOT_DIR/src" "$VENV_PY" "$BOOTSTRAP" &; exit 0
}

if [ -z "$PY312" ]; then
    osascript -e 'display dialog "Python 3.12 nest pas installé.\n\nInstallation automatique :\n• Homebrew\n• Python 3.12\n\n⏱ 5-15 minutes.\nCliquez OK." buttons {"OK"} default button "OK" with title "Ortho4XP V2.0" with icon note'

    BREW=/opt/homebrew/bin/brew
    [ ! -f "$BREW" ] && BREW=/usr/local/bin/brew
    [ ! -f "$BREW" ] && {
        osascript -e 'display notification "Installation Homebrew..." with title "Étape 1/3" subtitle "Ortho4XP V2.0"'
        NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" >> "$LOG" 2>&1
        BREW=/opt/homebrew/bin/brew
        [ ! -f "$BREW" ] && BREW=/usr/local/bin/brew
    }
    [ ! -f "$BREW" ] && {
        osascript -e 'display dialog "Impossible dinstaller Homebrew.\nhttps://brew.sh" buttons {"OK"} default button "OK" with title "Erreur" with icon stop'
        exit 1
    }

    osascript -e 'display notification "Installation Python 3.12..." with title "Étape 2/3" subtitle "Ortho4XP V2.0"'
    "$BREW" install python@3.12 python-tk@3.12 >> "$LOG" 2>&1
    PY312=$(find_py312)
    [ -z "$PY312" ] && {
        osascript -e 'display dialog "Python 3.12 na pas pu être installé.\nbrew install python@3.12 python-tk@3.12" buttons {"OK"} default button "OK" with title "Erreur" with icon stop'
        exit 1
    }
    osascript -e 'display notification "Python 3.12 installé ✓" with title "✅ Étape 3/3" subtitle "Ortho4XP V2.0"'
fi

[ ! -f "$VENV_PY" ] && {
    osascript -e 'display notification "Création environnement Python..." with title "Préparation" subtitle "Ortho4XP V2.0"'
    "$PY312" -m venv "$ROOT_DIR/venv" >> "$LOG" 2>&1
}

PY_USE="$VENV_PY"; [ ! -f "$PY_USE" ] && PY_USE="$PY312"
osascript -e 'display notification "Ouverture du Launcher..." with title "Lancement" subtitle "Ortho4XP V2.0"'
PYTHONPATH="$ROOT_DIR/src" "$PY_USE" "$BOOTSTRAP" &
"""
    exe_out.write_text(script, encoding="utf-8")
    exe_out.chmod(exe_out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print("  ✅ Shell script fallback créé.")


def create_windows_launcher():
    vbs_path = HERE / "Lanceur_Installation_Prerequis.vbs"
    vbs_path.write_text(VBS_SCRIPT, encoding="utf-8")
    print(f"  ✅ VBS créé : {vbs_path.name}")
    try:
        desktop  = Path(os.environ.get("USERPROFILE", "~")).expanduser() / "Desktop"
        shortcut = desktop / "Lanceur Installation Prerequis.lnk"
        ps = (f'$ws=$c=$ws.CreateShortcut("{shortcut}");'
              f'$c.TargetPath="{vbs_path}";'
              f'$c.WorkingDirectory="{HERE}";$c.Save()')
        subprocess.run(["powershell", "-Command",
                        f'$ws=New-Object -ComObject WScript.Shell;'
                        f'$sc=$ws.CreateShortcut("{shortcut}");'
                        f'$sc.TargetPath="{vbs_path}";'
                        f'$sc.WorkingDirectory="{HERE}";'
                        f'$sc.Description="Ortho4XP V2.0";$sc.Save()'],
                       capture_output=True, timeout=15)
        print("  ✅ Raccourci Bureau créé.")
    except Exception as e:
        print(f"  ℹ️  Raccourci Bureau : {e}")
    return vbs_path


def create_linux_launcher():
    import shutil
    sh_path = HERE / "Lanceur_Installation_Prerequis.sh"
    sh_path.write_text(
        f"""#!/bin/bash
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOOTSTRAP="$ROOT_DIR/INSTALL_PREREQUIS.py"
PYTHON=$(which python3.12 2>/dev/null || which python3 2>/dev/null)
if [ -z "$PYTHON" ]; then
    if command -v apt-get &>/dev/null; then
        sudo apt-get install -y python3.12 python3-tk python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python tk
    fi
    PYTHON=$(which python3.12 2>/dev/null || which python3)
fi
cd "$ROOT_DIR"
PYTHONPATH="$ROOT_DIR/src" "$PYTHON" "$BOOTSTRAP" &
""", encoding="utf-8")
    sh_path.chmod(sh_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    desktop_path = HERE / "Lanceur_Installation_Prerequis.desktop"
    desktop_path.write_text(
        f"[Desktop Entry]\nVersion=2.0\nName=Lanceur Installation Prerequis\n"
        f"Comment=Installation Ortho4XP V2.0\nExec={sh_path}\nPath={HERE}\n"
        f"Terminal=false\nType=Application\nCategories=Utility;\nStartupNotify=true\n",
        encoding="utf-8")
    desktop_path.chmod(
        desktop_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    try:
        apps = Path.home() / ".local" / "share" / "applications"
        apps.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(desktop_path), str(apps / "Lanceur_Installation_Prerequis.desktop"))
        print(f"  ✅ .desktop copié dans {apps}")
    except Exception:
        pass
    print(f"  ✅ .sh + .desktop créés.")
    return desktop_path


def main():
    print("=" * 58)
    print("  Ortho4XP V2.0 — Création du lanceur natif")
    print(f"  Plateforme : {SYSTEM} | Dossier : {HERE}")
    print("=" * 58)

    if not (HERE / "INSTALL_PREREQUIS.py").exists():
        print("❌ INSTALL_PREREQUIS.py introuvable — archive incomplète.")
        sys.exit(1)

    if SYSTEM == "Darwin":
        create_mac_app()
    elif SYSTEM == "Windows":
        create_windows_launcher()
    elif SYSTEM == "Linux":
        create_linux_launcher()
    else:
        print(f"⚠️  Plateforme non supportée : {SYSTEM}")
        sys.exit(1)

    print()
    print("✅ Lanceur créé. Double-clic sur :")
    if SYSTEM == "Darwin":    print("   Lanceur_Installation_Prerequis.app")
    elif SYSTEM == "Windows": print("   Lanceur_Installation_Prerequis.vbs")
    elif SYSTEM == "Linux":   print("   Lanceur_Installation_Prerequis.desktop")


if __name__ == "__main__":
    main()
