import json
import sqlite3
import threading
from datetime import datetime, timezone


class Database:
    def __init__(self, db_path="network.db"):
        self.db_path = db_path
        self._local = threading.local()
        self.init_db()

    def get_conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            self._local.conn = conn
        return self._local.conn

    def init_db(self):
        conn = self.get_conn()
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    latency REAL NOT NULL,
                    UNIQUE(source, destination),
                    FOREIGN KEY(source) REFERENCES nodes(name) ON DELETE CASCADE,
                    FOREIGN KEY(destination) REFERENCES nodes(name) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS route_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    total_latency REAL NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_history_source ON route_history(source);
                CREATE INDEX IF NOT EXISTS idx_history_dest ON route_history(destination);
                CREATE INDEX IF NOT EXISTS idx_history_date ON route_history(created_at);
            """)

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    # Nodes
    def add_node(self, name):
        conn = self.get_conn()
        with conn:
            cur = conn.execute("INSERT INTO nodes (name) VALUES (?);", (name,))
            return {"id": cur.lastrowid, "name": name}

    def get_node(self, name):
        conn = self.get_conn()
        row = conn.execute("SELECT id, name FROM nodes WHERE name = ?;", (name,)).fetchone()
        return dict(row) if row else None

    def list_nodes(self):
        conn = self.get_conn()
        rows = conn.execute("SELECT id, name FROM nodes ORDER BY id ASC;").fetchall()
        return [dict(r) for r in rows]

    def delete_node(self, node_id):
        conn = self.get_conn()
        with conn:
            cur = conn.execute("DELETE FROM nodes WHERE id = ?;", (node_id,))
            return cur.rowcount > 0

    # Edges
    def add_edge(self, source, destination, latency):
        conn = self.get_conn()
        with conn:
            cur = conn.execute(
                "INSERT INTO edges (source, destination, latency) VALUES (?, ?, ?);",
                (source, destination, latency),
            )
            return {
                "id": cur.lastrowid,
                "source": source,
                "destination": destination,
                "latency": latency,
            }

    def get_edge(self, source, destination):
        conn = self.get_conn()
        row = conn.execute(
            "SELECT id, source, destination, latency FROM edges WHERE source = ? AND destination = ?;",
            (source, destination),
        ).fetchone()
        return dict(row) if row else None

    def list_edges(self):
        conn = self.get_conn()
        rows = conn.execute("SELECT id, source, destination, latency FROM edges ORDER BY id ASC;").fetchall()
        return [dict(r) for r in rows]

    def delete_edge(self, edge_id):
        conn = self.get_conn()
        with conn:
            cur = conn.execute("DELETE FROM edges WHERE id = ?;", (edge_id,))
            return cur.rowcount > 0

    # History
    def log_query(self, source, destination, total_latency, path, created_at=None):
        if not created_at:
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        conn = self.get_conn()
        with conn:
            cur = conn.execute(
                "INSERT INTO route_history (source, destination, total_latency, path, created_at) VALUES (?, ?, ?, ?, ?);",
                (source, destination, total_latency, json.dumps(path), created_at),
            )
            return {
                "id": cur.lastrowid,
                "source": source,
                "destination": destination,
                "total_latency": total_latency,
                "path": path,
                "created_at": created_at,
            }

    def get_history(self, source=None, destination=None, limit=None, date_from=None, date_to=None):
        conn = self.get_conn()
        query = "SELECT id, source, destination, total_latency, path, created_at FROM route_history WHERE 1=1"
        params = []

        if source:
            query += " AND source = ?"
            params.append(source)
        if destination:
            query += " AND destination = ?"
            params.append(destination)
        if date_from:
            query += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND created_at <= ?"
            params.append(date_to)

        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": r["id"],
                "source": r["source"],
                "destination": r["destination"],
                "total_latency": r["total_latency"],
                "path": json.loads(r["path"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
