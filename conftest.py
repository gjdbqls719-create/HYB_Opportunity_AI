from __future__ import annotations

import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from urllib.parse import unquote, urlparse


_REPOSITORY_ROOT = Path(__file__).resolve().parent
_PRODUCTION_DATABASE = (
    _REPOSITORY_ROOT / "data" / "hyb_opportunity.db"
).resolve()
_TEST_DATABASE_ROOT = Path(tempfile.mkdtemp(prefix="hyb-pytest-databases-"))
_TEST_DATABASE = _TEST_DATABASE_ROOT / "hyb_opportunity.db"
_ORIGINAL_SQLITE_CONNECT = sqlite3.connect

os.environ["HYB_DATABASE_PATH"] = str(_TEST_DATABASE)
os.environ["HYB_PYTEST_PRODUCTION_DATABASE_GUARD"] = str(_PRODUCTION_DATABASE)


def _resolved_database_path(database: object) -> Path | None:
    try:
        value = os.fspath(database)
    except TypeError:
        return None
    if isinstance(value, bytes):
        value = os.fsdecode(value)
    if value == ":memory:":
        return None
    if value.startswith("file:"):
        parsed = urlparse(value)
        path = unquote(parsed.path)
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return Path(path).resolve()
    return Path(value).resolve()


def _guarded_sqlite_connect(database, *args, **kwargs):
    if _resolved_database_path(database) == _PRODUCTION_DATABASE:
        raise RuntimeError(
            "pytest refused access to the genuine production SQLite database"
        )
    return _ORIGINAL_SQLITE_CONNECT(database, *args, **kwargs)


sqlite3.connect = _guarded_sqlite_connect


def pytest_sessionfinish(session, exitstatus) -> None:
    sqlite3.connect = _ORIGINAL_SQLITE_CONNECT
    shutil.rmtree(_TEST_DATABASE_ROOT, ignore_errors=True)
