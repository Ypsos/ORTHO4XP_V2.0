#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_launcher.py — Version V2.0 Hybride (Mars 2026)
Crée un lanceur natif portable :
  • macOS   → Ortho4XP.app (Binaire universel, déplaçable)
  • Windows → Ortho4XP.vbs
  • Linux   → Ortho4XP.desktop
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
    VENV_PY  = HERE / "venv" / "Scripts" / "python.exe"
else:
    VENV_PY  = HERE / "venv" / "bin" / "python3"

def find_python() -> str:
    candidates = ["python3.12", "python3.11", "python3.10", "python3", "python"]
    for c in candidates:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                which = "where" if SYSTEM == "Windows" else "which"
                path = subprocess.run([which, c], capture_output=True, text=True).stdout.strip().splitlines()[0]
                return path
        except: continue
    return sys.executable

# ══════════════════════════════════════════════════════════════════════════
# macOS — Ortho4XP.app (VERSION BINAIRE UNIVERSELLE)
# ══════════════════════════════════════════════════════════════════════════

def create_mac_app():
    app = HERE / "Lanceur ORTHO4XP.app"
    macos_dir = app / "Contents" / "MacOS"
    resources_dir = app / "Contents" / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # 1. Création du code source C pour le lanceur relatif
    launcher_c = HERE / "launcher_mac.c"
    with open(launcher_c, "w") as f:
        f.write("""
#include <unistd.h>
#include <stdio.h>
#include <limits.h>
#include <libgen.h>
#include <stdint.h>

int main(int argc, char **argv) {
    char path[PATH_MAX];
    uint32_t size = sizeof(path);
    extern int _NSGetExecutablePath(char* buf, uint32_t* bufsize);
    if (_NSGetExecutablePath(path, &size) == 0) {
        char *base = dirname(path);      // MacOS/
        char *contents = dirname(base);  // Contents/
        char *app_root = dirname(contents); // Ortho4XP.app/
        char *root = dirname(app_root);     // Dossier Parent
        chdir(root);
        char *cmd[] = {"./venv/bin/python3", "Ortho4XP_Launcher.py", NULL};
        execv(cmd[0], cmd);
    }
    return 1;
}
""")

    # 2. Compilation
    exe_path = macos_dir / "Ortho4XP"
    print("  Compilation du moteur binaire macOS...")
    subprocess.run(["gcc", str(launcher_c), "-o", str(exe_path), "-framework", "Foundation"])
    if launcher_c.exists(): os.remove(launcher_c)
    
    exe_path.chmod(exe_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # 3. Info.plist
    (app / "Contents" / "Info.plist").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>CFBundleExecutable</key><string>Ortho4XP</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundleIdentifier</key><string>org.ortho4xp.v2</string>
    <key>CFBundleName</key><string>Ortho4XP</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
</dict></plist>""")

    # 4. Icône (Ton bloc original)
    try:
        from PIL import Image, ImageDraw
        iconset = resources_dir / "AppIcon.iconset"
        iconset.mkdir(exist_ok=True)
        for s in [16, 32, 64, 128, 256, 512]:
            img = Image.new("RGBA", (s, s), (30, 30, 46, 255))
            d = ImageDraw.Draw(img)
            m = s // 8
            d.ellipse([m, m, s-m, s-m], fill=(124, 158, 248, 255))
            cx, cy, sz = s//2, s//2, s//3
            d.polygon([(cx, cy-sz), (cx+sz//2, cy+sz//2), (cx, cy+sz//4), (cx-sz//2, cy+sz//2)], fill=(255, 255, 255, 230))
            img.save(iconset / f"icon_{s}x{s}.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(resources_dir / "AppIcon.icns")], capture_output=True)
    except: pass
    
    # Suppression de la quarantaine
    subprocess.run(["xattr", "-cr", str(app)], capture_output=True)
    return app

# ══════════════════════════════════════════════════════════════════════════
# Windows & Linux (Tes fonctions originales)
# ══════════════════════════════════════════════════════════════════════════

def create_windows_launcher(sys_python: str):
    vbs = HERE / "Lanceur ORTHO4XP.vbs"
    vbs_content = f'CreateObject("WScript.Shell").Run "cmd /c ""{VENV_PY}"" ""{HERE}/Ortho4XP_Launcher.py""", 0, False'
    vbs.write_text(vbs_content)
    return vbs

def create_linux_launcher(sys_python: str):
    sh = HERE / "ortho4xp_launch.sh"
    sh.write_text(f'#!/bin/bash\ncd "{HERE}"\n"./venv/bin/python3" "Ortho4XP_Launcher.py"',
                  encoding="utf-8")
    sh.chmod(sh.stat().st_mode | stat.S_IEXEC)
    desktop = HERE / "Lanceur ORTHO4XP.desktop"
    desktop.write_text(
        f"[Desktop Entry]\nVersion=2.0\nName=Lanceur ORTHO4XP\n"
        f"Exec={sh}\nPath={HERE}\nTerminal=false\nType=Application\n",
        encoding="utf-8")
    desktop.chmod(desktop.stat().st_mode | stat.S_IEXEC)
    return desktop

# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def main():
    print(f"--- Création du lanceur Ortho4XP V2.0 ({SYSTEM}) ---")
    sys_py = find_python()
    
    if SYSTEM == "Darwin":
        res = create_mac_app()
    elif SYSTEM == "Windows":
        res = create_windows_launcher(sys_py)
    else:
        res = create_linux_launcher(sys_py)
        
    print(f"\n✅ TERMINÉ ! Lanceur créé : {res.name}")
    print("L'application est maintenant portable et autonome.")

if __name__ == "__main__":
    main()