"""Verrou « un seul run à la fois » : refus d'un second processus, libération si le premier meurt."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pmmp_collector.runlock import RunAlreadyInProgress, run_lock

ROOT = Path(__file__).resolve().parents[1]

# Tente de prendre le verrou depuis un AUTRE processus (comme un second lancement).
TRY_LOCK = """
import sys
from pathlib import Path
from pmmp_collector.runlock import RunAlreadyInProgress, run_lock
try:
    with run_lock(Path(sys.argv[1])):
        print("ACQUIS", flush=True)
        if len(sys.argv) > 2:
            sys.stdin.readline()  # garde le verrou jusqu'à ce qu'on le tue
except RunAlreadyInProgress as exc:
    print("REFUSE", exc)
"""


def other_process(storage: Path, hold: bool = False, **kw):
    args = [sys.executable, "-c", TRY_LOCK, str(storage)] + (["hold"] if hold else [])
    env = {"PYTHONPATH": str(ROOT / "src"), "SYSTEMROOT": "C:\\Windows", "PATH": ""}
    return args, env


def test_second_process_is_refused_while_lock_is_held(tmp_path):
    with run_lock(tmp_path):
        args, env = other_process(tmp_path)
        out = subprocess.run(args, env=env, capture_output=True, text=True, timeout=30).stdout
        assert out.startswith("REFUSE") and "PID" in out  # le message indique qui tient le verrou
    args, env = other_process(tmp_path)  # verrou rendu à la sortie du bloc
    assert subprocess.run(args, env=env, capture_output=True, text=True, timeout=30).stdout.startswith("ACQUIS")


def test_lock_is_released_when_holder_is_killed(tmp_path):
    """Processus tué (arrêt brutal, redémarrage du PC) : le verrou ne reste pas bloqué."""
    args, env = other_process(tmp_path, hold=True)
    holder = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ACQUIS"
        with pytest.raises(RunAlreadyInProgress):
            with run_lock(tmp_path):
                pass
    finally:
        holder.kill()
        holder.wait(timeout=30)
    assert (tmp_path / ".crawl.lock").exists()  # le fichier reste, mais n'est plus verrouillé
    with run_lock(tmp_path):
        pass
