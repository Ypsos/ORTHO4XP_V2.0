# O4_Build_Transaction.py
# Système de sécurité ORTHO4XP V3
# Rôle : avant d'écrire un fichier final, travaille dans un dossier
#         temporaire (staging). Si tout va bien → copie finale.
#         Si quelque chose plante → rollback automatique.
# Compatible V2 : ne modifie rien dans les fichiers existants.
# ------------------------------------------------------------------

import os
import shutil
import time
import threading
from pathlib import Path
from typing import Optional

from O4_EventBus import event_bus, EventType


# ------------------------------------------------------------------
# États d'une transaction
# ------------------------------------------------------------------
TRANS_OPEN     = "open"
TRANS_COMMITED = "committed"
TRANS_ROLLED   = "rolled_back"


# ------------------------------------------------------------------
# La Transaction
# ------------------------------------------------------------------
class BuildTransaction:
    """
    Protège l'écriture des fichiers d'une tuile.

    Fonctionnement :
    ----------------
    1. On ouvre une transaction  → un dossier staging temporaire est créé
    2. On écrit tous les fichiers DANS le staging (jamais directement en final)
    3. Si tout va bien  → commit()  : les fichiers sont copiés vers leur destination finale
    4. Si ça plante     → rollback(): le staging est supprimé, rien n'est touché

    Utilisation typique :
    ---------------------
        tx = BuildTransaction(tile_id="48.00_2.00_ZL17",
                              final_dir="/path/to/tile/textures")
        with tx:
            chemin = tx.staging_path("ma_texture.dds")
            # ... écrire le fichier dans chemin ...
            tx.commit()
        # si une exception survient dans le bloc, rollback automatique
    """

    def __init__(self, tile_id: str, final_dir: str):
        self.tile_id   = tile_id
        self.final_dir = Path(final_dir)

        # Dossier temporaire de travail — nom unique par transaction
        _ts = int(time.time() * 1000)
        self._staging_dir = Path(final_dir) / f"_staging_{tile_id}_{_ts}"

        self.status    = TRANS_OPEN
        self._lock     = threading.Lock()
        self._files    : list = []   # fichiers écrits dans le staging
        self._backups  : dict = {}   # fichiers sauvegardés avant écrasement

    # ------------------------------------------------------------------
    # Gestionnaire de contexte (with BuildTransaction(...) as tx:)
    # ------------------------------------------------------------------
    def __enter__(self):
        self._open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Une exception s'est produite → rollback automatique
            self.rollback()
        elif self.status == TRANS_OPEN:
            # Bloc terminé sans commit explicite → rollback par sécurité
            self.rollback()
        return False  # on ne supprime pas l'exception

    # ------------------------------------------------------------------
    def _open(self):
        """Crée le dossier staging."""
        try:
            self._staging_dir.mkdir(parents=True, exist_ok=True)
            print(f"[Transaction] Staging ouvert : {self._staging_dir.name}")
        except Exception as e:
            raise RuntimeError(f"[Transaction] Impossible de créer le staging : {e}")

    # ------------------------------------------------------------------
    def staging_path(self, filename: str) -> str:
        """
        Retourne le chemin complet dans le staging pour un fichier donné.
        C'est ICI qu'on écrit — jamais directement dans final_dir.

        Exemple :
            chemin = tx.staging_path("texture_ZL17.dds")
            image.save(chemin)
        """
        path = self._staging_dir / filename
        with self._lock:
            self._files.append(filename)
        return str(path)

    # ------------------------------------------------------------------
    def commit(self) -> bool:
        """
        Copie tous les fichiers du staging vers final_dir.
        Supprime le staging ensuite.
        Retourne True si succès, False sinon.
        """
        if self.status != TRANS_OPEN:
            print(f"[Transaction] Commit ignoré — statut : {self.status}")
            return False

        with self._lock:
            try:
                # Créer le dossier final si nécessaire
                self.final_dir.mkdir(parents=True, exist_ok=True)

                # Sauvegarder les fichiers existants qu'on va écraser
                for filename in self._files:
                    dest = self.final_dir / filename
                    if dest.exists():
                        backup = self.final_dir / f"_bak_{filename}"
                        shutil.copy2(str(dest), str(backup))
                        self._backups[filename] = str(backup)

                # Copier staging → final
                copied = 0
                for filename in self._files:
                    src  = self._staging_dir / filename
                    dest = self.final_dir / filename
                    if src.exists():
                        shutil.copy2(str(src), str(dest))
                        copied += 1

                # Nettoyer les backups (commit réussi)
                for bak in self._backups.values():
                    try:
                        os.remove(bak)
                    except:
                        pass

                # Supprimer le staging
                shutil.rmtree(str(self._staging_dir), ignore_errors=True)

                self.status = TRANS_COMMITED
                print(f"[Transaction] ✅ Commit OK — {copied} fichier(s) → {self.final_dir.name}")

                event_bus.publish(EventType.TILE_COMPLETE, {
                    "tile":    self.tile_id,
                    "status":  "committed",
                    "files":   copied
                })
                return True

            except Exception as e:
                print(f"[Transaction] ❌ Commit échoué : {e} — rollback en cours")
                self._do_rollback()
                return False

    # ------------------------------------------------------------------
    def rollback(self):
        """
        Annule tout : supprime le staging, restaure les backups si besoin.
        Les fichiers finaux ne sont JAMAIS corrompus.
        """
        if self.status != TRANS_OPEN:
            return
        self._do_rollback()

    def _do_rollback(self):
        with self._lock:
            # Restaurer les backups si commit partiel avait commencé
            for filename, bak_path in self._backups.items():
                try:
                    dest = self.final_dir / filename
                    shutil.copy2(bak_path, str(dest))
                    os.remove(bak_path)
                except:
                    pass

            # Supprimer le staging
            shutil.rmtree(str(self._staging_dir), ignore_errors=True)

            self.status = TRANS_ROLLED
            print(f"[Transaction] ↩️  Rollback — staging supprimé, fichiers originaux préservés.")

            event_bus.publish(EventType.TILE_ERROR, {
                "tile":   self.tile_id,
                "status": "rolled_back"
            })


# ------------------------------------------------------------------
# Fonction utilitaire rapide
# ------------------------------------------------------------------
def safe_write(tile_id: str, final_dir: str,
               filename: str, write_fn) -> bool:
    """
    Raccourci pour écrire UN seul fichier de façon sécurisée.

    write_fn : fonction qui reçoit le chemin staging et écrit le fichier
               ex: lambda path: image.save(path)

    Retourne True si succès, False si échec (fichier original intact).

    Exemple :
        ok = safe_write(
            tile_id   = "48.00_2.00_ZL17",
            final_dir = "/path/to/textures",
            filename  = "texture.dds",
            write_fn  = lambda p: big_image.save(p)
        )
    """
    try:
        with BuildTransaction(tile_id, final_dir) as tx:
            path = tx.staging_path(filename)
            write_fn(path)
            return tx.commit()
    except Exception as e:
        print(f"[safe_write] Erreur : {e}")
        return False
