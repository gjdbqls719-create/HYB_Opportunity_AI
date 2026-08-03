"""Serve the web composition root against an explicit local validation DB."""
from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from storage.price_history import DEFAULT_DATABASE_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve an existing local PR23-C validation database")
    parser.add_argument("--database", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    database = Path(args.database).expanduser().resolve()
    if database == Path(DEFAULT_DATABASE_PATH).resolve():
        parser.error("local validation server refuses the production default database")
    if not database.is_file():
        parser.error("local validation database does not exist")
    import app.web as web
    web.DEFAULT_DATABASE_PATH = str(database)
    uvicorn.run(web.app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
