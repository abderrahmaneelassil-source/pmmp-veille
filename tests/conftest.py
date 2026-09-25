"""Configuration commune : environnement de test isolé, aucune requête réseau."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
_TMP = tempfile.mkdtemp(prefix="pmmp_tests_")

# Doit précéder tout import de pmmp_collector (la config est lue à l'import de settings).
os.environ.update({
    "PMMP_MODE": "test",
    "PMMP_BASE_URL": "https://www.marchespublics.gov.ma/pmmp/",
    "PMMP_USER_AGENT": "TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)",
    "PMMP_DOWNLOAD_DELAY": "3",
    "PMMP_ALLOWED_WINDOW": "06:00-10:00",
    "PMMP_TIMEZONE": "Africa/Casablanca",
    "PMMP_CB_MAX_CONSECUTIVE": "3",
    "PMMP_DATABASE_URL": "",
    "PMMP_STORAGE_DIR": str(Path(_TMP) / "storage"),
    "PMMP_FIXTURES_DIR": str(Path(_TMP) / "fixtures"),
})
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # paquet api/ (API de consultation)


@pytest.fixture
def fixture_html():
    def _read(rel: str) -> str:
        return (FIXTURES / rel).read_text(encoding="utf-8")
    return _read
