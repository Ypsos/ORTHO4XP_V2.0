#!/bin/bash
# ============================================================
#  ORTHO4XP V2 — Lanceur universel Linux
#  Double-cliquez sur ce fichier pour démarrer
#  (ou chmod +x LANCER_ORTHO4XP.sh && ./LANCER_ORTHO4XP.sh)
# ============================================================
cd "$(dirname "$0")"
if command -v python3.12 &>/dev/null; then
    python3.12 INSTALL_PREREQUIS.py
elif command -v python3 &>/dev/null; then
    python3 INSTALL_PREREQUIS.py
else
    echo "Python introuvable. Installez Python 3.12 : sudo apt install python3.12"
    read -p "Appuyez sur Entrée pour quitter..."
fi
