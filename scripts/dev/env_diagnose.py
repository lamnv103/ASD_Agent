"""Explain WHY the project cannot reach its database, layer by layer, without printing secrets.

    .venv-embedding\\Scripts\\python.exe -B scripts/dev/env_diagnose.py

Order: dependencies -> database configuration -> network/connection -> authentication -> database
name -> release integrity (rag.retriever health). Each step returns a stable code; only the first
failing step is reported. The connection string and server messages are never printed.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_MODULES = ("psycopg2", "dotenv", "certifi", "yaml", "tokenizers", "transformers", "jinja2", "bs4")

HINTS = {
    "ok": "Database reachable and release integrity verified.",
    "dependency_missing": "A required package is missing: rebuild the venv from requirements.lock.txt (.\\tasks.ps1 setup) and run scripts/dev/check_env.py.",
    "database_config": "deployments/database.env is missing, incomplete or selects another collection/database.",
    "database_unreachable": "No PostgreSQL answered (container stopped, wrong host/port, firewall). Try .\\tasks.ps1 db-up.",
    "database_auth": "PostgreSQL rejected the credentials in deployments/database.env (user/password).",
    "database_missing": "The server answered but the database named in deployments/database.env does not exist.",
    "database_error": "PostgreSQL returned another error (details omitted to avoid leaking connection data).",
    "database_integrity": "Connected, but the collection/vectors do not match the pinned release.",
    "config_invalid": "deployments/retriever.json is unreadable or not the approved release.",
}


def classify_operational(message: str) -> str:
    m = message.lower()
    if "password authentication failed" in m or "no password supplied" in m or "authentication failed" in m:
        return "database_auth"
    if "database" in m and "does not exist" in m:
        return "database_missing"
    if any(s in m for s in ("connection refused", "could not connect", "timeout expired", "timed out",
                            "could not translate host name", "server closed the connection", "no route to host",
                            "connection to server", "is the server running")):
        return "database_unreachable"
    return "database_error"


def diagnose(database_env: Path | None = None) -> dict:
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except ImportError:
            return dict(ok=False, code="dependency_missing", detail=name)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import dotenv_values
        import psycopg2
        from rag.retriever import PostgresRetriever, RetrievalError
    except ImportError as exc:
        return dict(ok=False, code="dependency_missing", detail=getattr(exc, "name", None) or "rag.retriever")
    try:
        retriever = PostgresRetriever(database_env=database_env)
    except RetrievalError as exc:
        return dict(ok=False, code=exc.code, detail=None)
    env_path = retriever.database_env
    if not env_path.is_file():
        return dict(ok=False, code="database_config", detail="file not found")
    dsn = dotenv_values(env_path, interpolate=False).get("RAG_DATABASE_URL")
    if not dsn:
        return dict(ok=False, code="database_config", detail="RAG_DATABASE_URL missing")
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except psycopg2.OperationalError as exc:
        return dict(ok=False, code=classify_operational(str(exc)), detail=None)
    except psycopg2.Error:
        return dict(ok=False, code="database_error", detail=None)
    except Exception:  # malformed DSN etc.
        return dict(ok=False, code="database_config", detail="RAG_DATABASE_URL not usable")
    try:
        if conn.info.dbname != "asd_rag":
            return dict(ok=False, code="database_config", detail="expected the asd_rag database")
    finally:
        conn.close()
    try:
        retriever.health()
    except RetrievalError as exc:
        return dict(ok=False, code=exc.code, detail=None)
    return dict(ok=True, code="ok", detail=None)


def describe(result: dict) -> str:
    detail = f" ({result['detail']})" if result.get("detail") else ""
    return f"[{result['code']}]{detail} {HINTS.get(result['code'], '')}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    result = diagnose()
    print(json.dumps(result))
    print(describe(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
