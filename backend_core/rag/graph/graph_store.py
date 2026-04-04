"""rag/graph/graph_store.py
SQLite 知识图谱存储（禁止 Neo4j / networkx，2G 内存友好）。
表结构：kg_nodes + kg_edges
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

_DDL_NODES = """
CREATE TABLE IF NOT EXISTS kg_nodes (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    node_type      TEXT NOT NULL DEFAULT 'concept',
    properties     TEXT NOT NULL DEFAULT '{}',
    embedding_text TEXT NOT NULL DEFAULT ''
);
"""

_DDL_EDGES = """
CREATE TABLE IF NOT EXISTS kg_edges (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    src_id   TEXT    NOT NULL,
    dst_id   TEXT    NOT NULL,
    relation TEXT    NOT NULL,
    weight   REAL    NOT NULL DEFAULT 1.0,
    FOREIGN KEY (src_id) REFERENCES kg_nodes(id),
    FOREIGN KEY (dst_id) REFERENCES kg_nodes(id)
);
"""

_DDL_IDX = """
CREATE INDEX IF NOT EXISTS idx_edges_src ON kg_edges(src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON kg_edges(dst_id);
"""


def _conn() -> sqlite3.Connection:
    """获取 SQLite 连接，自动建表。"""
    db_path = settings.KG_SQLITE_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(_DDL_NODES)
        conn.execute(_DDL_EDGES)
        conn.executescript(_DDL_IDX)
    return conn


# ── 写入 ──────────────────────────────────────────────────────────────────

def add_node(
    node_id:        str,
    name:           str,
    node_type:      str = "concept",
    properties:     Optional[Dict[str, Any]] = None,
    embedding_text: str = "",
) -> None:
    """插入或替换节点。"""
    c = _conn()
    try:
        with c:
            c.execute(
                "INSERT OR REPLACE INTO kg_nodes "
                "(id, name, node_type, properties, embedding_text) VALUES (?,?,?,?,?)",
                (node_id, name, node_type, json.dumps(properties or {}), embedding_text),
            )
    finally:
        c.close()


def add_edge(
    src_id:   str,
    dst_id:   str,
    relation: str,
    weight:   float = 1.0,
) -> None:
    """插入边（允许重复）。"""
    c = _conn()
    try:
        with c:
            c.execute(
                "INSERT INTO kg_edges (src_id, dst_id, relation, weight) VALUES (?,?,?,?)",
                (src_id, dst_id, relation, weight),
            )
    finally:
        c.close()


# ── 读取 ──────────────────────────────────────────────────────────────────

def get_node_count() -> int:
    c = _conn()
    try:
        return c.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
    finally:
        c.close()


def search_nodes_by_keywords(
    keywords: List[str],
    limit:    int = 5,
) -> List[Dict[str, Any]]:
    """在 name / embedding_text 中做 LIKE 匹配。"""
    if not keywords:
        return []

    c = _conn()
    try:
        clause = " OR ".join(
            ["(name LIKE ? OR embedding_text LIKE ?)"] * len(keywords)
        )
        params: List[str] = []
        for kw in keywords:
            like = f"%{kw}%"
            params += [like, like]

        rows = c.execute(
            f"SELECT id, name, node_type, properties, embedding_text "
            f"FROM kg_nodes WHERE {clause} LIMIT ?",
            params + [limit],
        ).fetchall()

        return [_row_to_dict(r) for r in rows]
    finally:
        c.close()


def get_one_hop_neighbors(
    node_ids: List[str],
    limit:    int = 10,
) -> List[Dict[str, Any]]:
    """返回给定节点集合的 1-hop 邻居（去除种子节点自身）。"""
    if not node_ids:
        return []

    c = _conn()
    try:
        ph = ",".join("?" * len(node_ids))
        rows = c.execute(
            f"""
            SELECT DISTINCT
                n.id, n.name, n.node_type, n.properties, n.embedding_text,
                e.relation, e.weight
            FROM kg_edges e
            JOIN kg_nodes n
              ON (e.dst_id = n.id OR e.src_id = n.id)
            WHERE (e.src_id IN ({ph}) OR e.dst_id IN ({ph}))
              AND n.id NOT IN ({ph})
            ORDER BY e.weight DESC
            LIMIT ?
            """,
            node_ids + node_ids + node_ids + [limit],
        ).fetchall()

        return [_row_to_dict(r) for r in rows]
    finally:
        c.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["properties"] = json.loads(d.get("properties", "{}") or "{}")
    except json.JSONDecodeError:
        d["properties"] = {}
    return d