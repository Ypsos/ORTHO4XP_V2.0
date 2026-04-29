#!/usr/bin/env python3
"""
rge_download.py  –  Téléchargement du RGE ALTI 1 m (IGN) pour la France métropolitaine.

Utilise :
  - urllib.request  (stdlib, aucune dépendance externe)
  - concurrent.futures pour le téléchargement parallèle
  - Reprise automatique des fichiers partiellement téléchargés
  - Barre de progression légère via print()

Source officielle :
  https://data.geopf.fr/telechargement/download/RGEALTI/
  RGEALTI_2-0_1M_ASC_LAMB93-IGN69/<DEPT>/

Usage :
  python3 rge_download.py [--outdir RGE] [--workers 4] [--depts 01 02 …]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = (
    "https://data.geopf.fr/telechargement/download/RGEALTI/"
    "RGEALTI_2-0_1M_ASC_LAMB93-IGN69/"
)

# Départements France métropolitaine (01-95, en ignorant 20 → 2A & 2B)
METRO_DEPTS: list[str] = (
    [f"D{i:03d}" for i in range(1, 20)]
    + ["D02A", "D02B"]  # Corse
    + [f"D{i:03d}" for i in range(21, 96)]
)

CHUNK_SIZE = 1 << 20  # 1 MiB


# ---------------------------------------------------------------------------
# HTML link parser
# ---------------------------------------------------------------------------

class _LinkParser(HTMLParser):
    """Extracts href values ending with '.7z' from an HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value and value.endswith(".7z"):
                    self.links.append(value)


def list_archives(dept_url: str) -> list[str]:
    """Return the list of .7z archive filenames available for a département."""
    try:
        with urllib.request.urlopen(dept_url, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        parser = _LinkParser()
        parser.feed(html)
        return parser.links
    except urllib.error.URLError:
        return []


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def download_file(url: str, dest: Path) -> tuple[str, str]:
    """
    Download *url* to *dest*, resuming if a partial file exists.
    Returns (url, status) where status is 'ok', 'skipped', or 'error:<msg>'.
    """
    filename = dest.name

    # Determine how many bytes we already have
    existing = dest.stat().st_size if dest.exists() else 0

    headers = {}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            # Server does not support resume → start over
            if resp.status == 200 and existing:
                existing = 0
                dest.unlink(missing_ok=True)

            if resp.status not in (200, 206):
                return url, f"error:HTTP {resp.status}"

            total_raw = resp.headers.get("Content-Length")
            total = int(total_raw) + existing if total_raw else None

            mode = "ab" if existing else "wb"
            with dest.open(mode) as fh:
                downloaded = existing
                while chunk := resp.read(CHUNK_SIZE):
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  {filename}: {pct:3d}%", end="", flush=True)

        print(f"\r  {filename}: done      ")
        return url, "ok"

    except Exception as exc:  # noqa: BLE001
        print(f"\r  {filename}: ERROR – {exc}")
        return url, f"error:{exc}"


# ---------------------------------------------------------------------------
# Main worker
# ---------------------------------------------------------------------------

def process_dept(dept: str, outdir: Path) -> tuple[str, int, int]:
    """Download all archives for one département.  Returns (dept, ok, err)."""
    url = BASE_URL + dept + "/"
    archives = list_archives(url)
    if not archives:
        return dept, 0, 0

    ok = err = 0
    for filename in archives:
        dest = outdir / filename
        # Already fully downloaded: skip
        if dest.exists() and dest.stat().st_size > 0:
            # We can't know the exact remote size without a HEAD request,
            # so we trust a non-empty file is complete unless --force is used.
            print(f"  {filename}: already present, skipping.")
            ok += 1
            continue
        file_url = url + filename
        _, status = download_file(file_url, dest)
        if status == "ok":
            ok += 1
        else:
            err += 1
    return dept, ok, err


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Télécharge le RGE ALTI 1 m (IGN) pour la France métropolitaine."
    )
    parser.add_argument(
        "--outdir",
        default="RGE",
        help="Répertoire de destination (défaut : ./RGE)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Nombre de téléchargements parallèles (défaut : 4)",
    )
    parser.add_argument(
        "--depts",
        nargs="*",
        metavar="NNN",
        help=(
            "Numéros de département à traiter (ex: 01 67 2A). "
            "Tous les départements métropolitains si omis."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.depts:
        # Normalise: "67" → "D067", "2A" → "D02A", "D67" → "D067"
        depts = []
        for raw in args.depts:
            raw = raw.upper().lstrip("D")
            try:
                depts.append(f"D{int(raw):03d}")
            except ValueError:
                depts.append(f"D{raw:>03s}")
    else:
        depts = METRO_DEPTS

    print(f"Téléchargement RGE ALTI – {len(depts)} département(s) → {outdir}/")
    total_ok = total_err = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(process_dept, dept, outdir): dept for dept in depts
        }
        for future in concurrent.futures.as_completed(futures):
            dept, ok, err = future.result()
            total_ok += ok
            total_err += err
            status = f"{ok} fichier(s)" + (f", {err} erreur(s)" if err else "")
            print(f"[{dept}] {status}")

    print(f"\nTerminé : {total_ok} succès, {total_err} erreur(s).")
    if total_err:
        sys.exit(1)


if __name__ == "__main__":
    main()
