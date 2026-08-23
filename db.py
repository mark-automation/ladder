"""SQLite access helpers (stdlib sqlite3, Row factory) — blueprint S adapted to MVP."""
import os, sqlite3, threading

DB_PATH = os.environ.get("LADDER_DB",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder.db"))
_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# FastAPI runs sync endpoints in a threadpool → allow cross-thread reuse and
# serialize writers (single-process MVP; Postgres replaces this at scale).
_LOCK = threading.Lock()


def connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    with open(_SCHEMA, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _LOCK:
        return conn.execute(sql, params).fetchall()


def q1(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _LOCK:
        return conn.execute(sql, params).fetchone()


def ex(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _LOCK:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def jloads(s, default):
    import json
    try:
        return json.loads(s)
    except Exception:
        return default
