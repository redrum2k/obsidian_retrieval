import contextlib
import fcntl
import os
import sqlite3

from .common import VaultError

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO meta VALUES('generation','0');
CREATE TABLE IF NOT EXISTS documents(
 id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, hash TEXT NOT NULL,
 size INTEGER, mtime INTEGER, role TEXT, project TEXT, title TEXT, aliases TEXT,
 author TEXT, status TEXT, warnings TEXT, cache_key TEXT, extractor TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sections(
 id TEXT PRIMARY KEY, document_id TEXT, revision TEXT, ordinal INTEGER,
 heading TEXT, text TEXT, locator TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
 section_id UNINDEXED, title, aliases, heading, text, tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS links(
 document_id TEXT, revision TEXT, target TEXT,
 PRIMARY KEY(document_id,revision,target)
);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT, path TEXT, project TEXT,
 revision TEXT, reason TEXT, observed TEXT
);
CREATE TABLE IF NOT EXISTS work(
 document_id TEXT, revision TEXT, state TEXT, proposal_id TEXT,
 PRIMARY KEY(document_id,revision)
);
CREATE TABLE IF NOT EXISTS proposals(
 id TEXT PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL,
 delivery TEXT DEFAULT 'pending', created TEXT, signature TEXT
);
CREATE TABLE IF NOT EXISTS actions(
 proposal_id TEXT, ordinal INTEGER, state TEXT, PRIMARY KEY(proposal_id,ordinal)
);
CREATE TABLE IF NOT EXISTS metrics(name TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""


class Store:
    def __init__(self, state):
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(state, 0o700)
        self.state = state
        self.db = sqlite3.connect(state / "vault.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def lock(self):
        with (self.state / "operation.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise VaultError(
                    "busy", "Another operation is running; retry this trigger."
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def meta(self, key, value=None):
        if value is not None:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def count(self, name, amount=1):
        self.db.execute(
            "INSERT INTO metrics VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value",
            (name, amount),
        )
