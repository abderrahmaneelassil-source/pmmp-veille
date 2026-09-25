"""Verrou « un seul run à la fois » (lancement manuel pendant la tâche planifiée, par ex.).

Verrou du système d'exploitation sur storage/.crawl.lock : il est libéré
automatiquement quand le processus se termine, même tué ou si le PC redémarre.
Il ne peut donc pas rester bloqué. Le fichier lui-même peut rester sur le disque :
seule compte la présence d'un processus qui le tient.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

LOCK_NAME = ".crawl.lock"  # distinct de storage/.run.lock pris par flock dans run_nightly.sh
INFO_NAME = ".crawl.pid"


class RunAlreadyInProgress(RuntimeError):
    """Un autre run tient déjà le verrou."""


def _try_lock(fh) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextmanager
def run_lock(storage_dir: Path):
    """Tient le verrou pendant le bloc ; RunAlreadyInProgress si un autre run le tient."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    info = storage_dir / INFO_NAME
    fh = open(storage_dir / LOCK_NAME, "a+")
    if not _try_lock(fh):
        fh.close()
        try:
            holder = info.read_text(encoding="utf-8").strip()
        except OSError:
            holder = "inconnu"
        raise RunAlreadyInProgress(holder)
    try:
        info.write_text(f"PID {os.getpid()}, démarré le {datetime.now().astimezone():%Y-%m-%d %H:%M:%S}",
                        encoding="utf-8")
        yield
    finally:
        fh.close()  # libère le verrou
