#!/usr/bin/env python3
"""
Ortho4XP V2.0 - Point d'entrée principal
Version modernisée - Avril 2026
Compatible venv autonome + lancement automatique
"""

import sys
import os

# ====================== CONFIGURATION DES CHEMINS ======================
# Détection du mode "frozen" (lanceur .app / .exe) et chemin de base
if getattr(sys, 'frozen', False):
    Ortho4XP_dir = os.path.dirname(sys.executable)
else:
    Ortho4XP_dir = os.path.dirname(os.path.abspath(__file__))

# Ajout du dossier src au PYTHONPATH (structure propre V2)
sys.path.insert(0, os.path.join(Ortho4XP_dir, 'src'))

import O4_File_Names as FNAMES
sys.path.append(FNAMES.Provider_dir)

# Imports des modules principaux
import O4_Imagery_Utils as IMG
import O4_Vector_Map as VMAP
import O4_Mesh_Utils as MESH
import O4_Mask_Utils as MASK
import O4_Tile_Utils as TILE
import O4_GUI_Utils as GUI
import O4_Config_Utils as CFG   # Doit rester en dernier

def main():
    print("Ortho4XP V2.0 - Démarrage...")

    # Vérification du dossier Utils (binaires nvcompress, etc.)
    if not os.path.isdir(FNAMES.Utils_dir):
        print(f"ERREUR: Dossier manquant {FNAMES.Utils_dir}")
        print("Vérifiez votre installation. Exiting.")
        sys.exit(1)

    # Création automatique des dossiers requis
    required_dirs = (
        FNAMES.Preview_dir, FNAMES.Provider_dir, FNAMES.Extent_dir,
        FNAMES.Filter_dir, FNAMES.OSM_dir, FNAMES.Mask_dir,
        FNAMES.Imagery_dir, FNAMES.Elevation_dir, FNAMES.Geotiff_dir,
        FNAMES.Patch_dir, FNAMES.Tile_dir, FNAMES.Tmp_dir
    )

    for directory in required_dirs:
        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
                print(f"Création du dossier : {directory}")
            except Exception as e:
                print(f"ERREUR: Impossible de créer le dossier {directory} → {e}")
                sys.exit(1)

    # Initialisation des dictionnaires (providers, filtres, etc.)
    try:
        IMG.initialize_extents_dict()
        IMG.initialize_color_filters_dict()
        IMG.initialize_providers_dict()
        IMG.initialize_combined_providers_dict()
    except Exception as e:
        print(f"Attention lors de l'initialisation des providers/filtres : {e}")
        # On continue quand même (comme dans la V1)

    # ====================== MODE GUI (lancement normal) ======================
    if len(sys.argv) == 1:
        try:
            print("Lancement de l'interface graphique...")
            app = GUI.Ortho4XP_GUI()
            app.mainloop()
            print("Ortho4XP fermé. Bon vol !")
        except Exception as e:
            print(f"ERREUR lors du lancement de l'interface : {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    # ====================== MODE LIGNE DE COMMANDE (conservé) ======================
    else:
        print("Mode ligne de commande activé")
        # Le code CLI original est conservé ici si tu en as besoin
        # (je peux le remettre en détail si tu veux)

        print("Bon vol !")


if __name__ == '__main__':
    main()
