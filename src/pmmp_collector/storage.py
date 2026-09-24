"""Stockage disque : HTML brut archivé, fixtures de test, fichiers DCE."""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def safe_name(value: str, max_len: int = 100) -> str:
    value = unicodedata.normalize("NFC", value or "")
    value = re.sub(r"[^\w.-]+", "_", value).strip("._")
    return value[:max_len] or "sans_nom"


def consultation_key(org: str | None, ref: str | None) -> str:
    return f"{safe_name(org or 'inconnu')}__{safe_name(ref or 'inconnu')}"


class HtmlArchiver:
    """Écrit les pages telles que reçues (octets bruts) + un index JSONL pour la ré-analyse."""

    def __init__(self, root: Path, run_stamp: str, fixtures_dir: Path | None = None):
        self.run_dir = root / run_stamp
        self.index_path = root / "index.jsonl"
        self.fixtures_dir = fixtures_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def save(self, response, kind: str, key: str) -> Path | None:
        path = self.run_dir / kind / f"{safe_name(key)}.html"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.body)
            with self.index_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "path": str(path),
                    "url": response.url,
                    "method": response.request.method if response.request else None,
                    "status": response.status,
                    "kind": kind,
                    "key": key,
                    "fetched_at": datetime.now().astimezone().isoformat(),
                    "sha256": hashlib.sha256(response.body).hexdigest(),
                }, ensure_ascii=False) + "\n")
            if self.fixtures_dir is not None:
                fixture = self.fixtures_dir / kind / path.name
                fixture.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, fixture)
            return path
        except OSError:
            logger.exception("Échec d'archivage HTML (%s %s)", kind, key)
            return None


_CD_FILENAME_STAR = re.compile(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", re.I)
_CD_FILENAME = re.compile(r'filename\s*=\s*"?([^";]+)"?', re.I)


def filename_from_response(response, index: int) -> str:
    cd = (response.headers.get("Content-Disposition") or b"").decode("latin-1")
    m = _CD_FILENAME_STAR.search(cd)
    name = unquote(m.group(1)) if m else None
    if not name:
        m = _CD_FILENAME.search(cd)
        if m:
            raw = m.group(1)
            try:  # en-têtes souvent en UTF-8 décodé à tort en latin-1
                name = raw.encode("latin-1").decode("utf-8")
            except UnicodeError:
                name = raw
    if not name:
        base = Path(urlparse(response.url).path).name
        if base and "." in base and not base.endswith(".php"):
            name = base
    if not name:
        ctype = (response.headers.get("Content-Type") or b"").decode("latin-1").split(";")[0].strip()
        name = f"dce_{index}{mimetypes.guess_extension(ctype) or '.bin'}"
    return safe_name(name, max_len=150)


class DceStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, org: str, ref: str) -> Path:
        return self.root / consultation_key(org, ref)

    def existing(self, org: str, ref: str) -> list[str]:
        folder = self.folder(org, ref)
        if not folder.is_dir():
            return []
        return sorted(str(p) for p in folder.iterdir() if p.is_file() and not p.name.endswith(".part"))

    def save(self, org: str, ref: str, filename: str, body: bytes) -> Path:
        folder = self.folder(org, ref)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / filename
        n = 1
        while target.exists():
            target = folder / f"{Path(filename).stem}_{n}{Path(filename).suffix}"
            n += 1
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(body)
        tmp.replace(target)
        return target
