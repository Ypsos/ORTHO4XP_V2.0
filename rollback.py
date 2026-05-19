"""
rollback.py
Ortho4XP V3 — Lot A / Script utilitaire
Auteur : Roland (Ypsos) — Codage : Claude (Anthropic AI)
Version : 1.0 — Mai 2026

Usage :
    python rollback.py                      → liste toutes les sauvegardes
    python rollback.py <fichier>            → rollback 1-clic (dernière sauvegarde)
    python rollback.py <fichier> <timestamp>→ rollback vers une sauvegarde précise
    python rollback.py --list <fichier>     → liste les sauvegardes de ce fichier

Exemples :
    python rollback.py O4_DSF_Utils.py
    python rollback.py O4_DSF_Utils.py 20260518_143022
    python rollback.py --list O4_DSF_Utils.py
"""

import sys
import os

# Ajouter le dossier courant au path pour trouver O4_Backup_Manager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from O4_Backup_Manager import rollback_last, rollback_to, list_backups
except ImportError:
    print("ERREUR : O4_Backup_Manager.py introuvable.")
    print("Assurez-vous que rollback.py est dans le même dossier que O4_Backup_Manager.py")
    sys.exit(1)


def _print_backups(entries, title="Sauvegardes disponibles"):
    """Affiche la liste des sauvegardes de façon lisible."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    if not entries:
        print("  (aucune sauvegarde trouvée)")
        return
    for i, e in enumerate(entries, 1):
        size_kb = e.get("size_bytes", 0) / 1024
        print(f"  [{i:2d}] {e.get('timestamp','?')}  "
              f"{os.path.basename(e.get('original','?'))}  "
              f"({size_kb:.1f} Ko)  [{e.get('reason','?')}]")
    print(f"{'='*60}\n")


def main():
    args = sys.argv[1:]

    # ── Aucun argument → liste tout ──────────────────────────────────────────
    if not args:
        entries = list_backups()
        _print_backups(entries, title="Toutes les sauvegardes Ortho4XP")
        print("Usage : python rollback.py <fichier> [timestamp]")
        return

    # ── --list <fichier> ─────────────────────────────────────────────────────
    if args[0] == "--list":
        if len(args) < 2:
            print("Usage : python rollback.py --list <fichier>")
            sys.exit(1)
        filepath = args[1]
        entries  = list_backups(filepath)
        _print_backups(entries, title=f"Sauvegardes de {os.path.basename(filepath)}")
        return

    # ── rollback 1-clic ou ciblé ─────────────────────────────────────────────
    filepath = args[0]

    if not os.path.isabs(filepath):
        filepath = os.path.abspath(filepath)

    if len(args) == 1:
        # Rollback vers la dernière sauvegarde
        print(f"\nRollback 1-clic : {os.path.basename(filepath)}")
        entries = list_backups(filepath)
        if not entries:
            print(f"ERREUR : aucune sauvegarde trouvée pour {os.path.basename(filepath)}")
            sys.exit(1)
        last = entries[0]  # déjà trié du plus récent au plus ancien
        print(f"  → Restauration depuis : {os.path.basename(last.get('backup_path','?'))}")
        print(f"  → Timestamp           : {last.get('timestamp','?')}")
        print(f"  → Motif               : {last.get('reason','?')}")
        confirm = input("\nConfirmer ? (o/n) : ").strip().lower()
        if confirm not in ("o", "oui", "y", "yes"):
            print("Annulé.")
            return
        ok = rollback_last(filepath)
        if ok:
            print(f"\n✅ Rollback réussi : {os.path.basename(filepath)} restauré.")
        else:
            print(f"\n❌ Rollback échoué. Vérifiez les logs.")
            sys.exit(1)

    elif len(args) == 2:
        # Rollback vers un timestamp précis
        timestamp = args[1]
        print(f"\nRollback ciblé : {os.path.basename(filepath)} → {timestamp}")
        confirm = input("Confirmer ? (o/n) : ").strip().lower()
        if confirm not in ("o", "oui", "y", "yes"):
            print("Annulé.")
            return
        ok = rollback_to(filepath, timestamp)
        if ok:
            print(f"\n✅ Rollback ciblé réussi.")
        else:
            print(f"\n❌ Rollback ciblé échoué. Timestamp introuvable ou fichier manquant.")
            sys.exit(1)

    else:
        print("Usage : python rollback.py <fichier> [timestamp]")
        sys.exit(1)


if __name__ == "__main__":
    main()
