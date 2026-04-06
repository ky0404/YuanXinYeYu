#!/usr/bin/env python3
"""scripts/migrate_feedback.py
为 feedback_records 表新增 v3.1 字段：
  refs_json TEXT NULL
  rag_route VARCHAR(30) NULL
  risk_level VARCHAR(20) NULL
  cached INTEGER NULL

适用：SQLite 和 MySQL（自动检测）。
已存在的列会跳过，不会报错。

运行：
  cd /root/emotion_analysis_service
  python scripts/migrate_feedback.py
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config.settings import settings

NEW_COLUMNS = [
    ("refs_json",  "TEXT"),
    ("rag_route",  "VARCHAR(30)"),
    ("risk_level", "VARCHAR(20)"),
    ("cached",     "INTEGER"),
]

def migrate_sqlite(db_url: str) -> None:
    import sqlite3
    db_path = db_url.replace("sqlite:///", "")
    conn    = sqlite3.connect(db_path)
    cur     = conn.cursor()

    cur.execute("PRAGMA table_info(feedback_records)")
    existing = {row[1] for row in cur.fetchall()}

    for col_name, col_type in NEW_COLUMNS:
        if col_name not in existing:
            sql = f"ALTER TABLE feedback_records ADD COLUMN {col_name} {col_type} NULL"
            print(f"  执行: {sql}")
            cur.execute(sql)
        else:
            print(f"  跳过（已存在）: {col_name}")

    conn.commit()
    conn.close()
    print("✅ SQLite 迁移完成")


def migrate_mysql(db_url: str) -> None:
    import pymysql
    # 解析 mysql+pymysql://user:pass@host:port/dbname
    url = db_url.replace("mysql+pymysql://", "")
    auth, rest = url.split("@", 1)
    user, pwd  = auth.split(":", 1)
    host_rest, dbname = rest.rsplit("/", 1)
    if ":" in host_rest:
        host, port_str = host_rest.rsplit(":", 1)
        port = int(port_str)
    else:
        host, port = host_rest, 3306

    conn = pymysql.connect(host=host, port=port, user=user, password=pwd, database=dbname)
    cur  = conn.cursor()

    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='feedback_records' AND TABLE_SCHEMA=%s",
        (dbname,),
    )
    existing = {row[0] for row in cur.fetchall()}

    for col_name, col_type in NEW_COLUMNS:
        if col_name not in existing:
            sql = f"ALTER TABLE feedback_records ADD COLUMN {col_name} {col_type} NULL"
            print(f"  执行: {sql}")
            cur.execute(sql)
        else:
            print(f"  跳过（已存在）: {col_name}")

    conn.commit()
    conn.close()
    print("✅ MySQL 迁移完成")


if __name__ == "__main__":
    url = settings.DATABASE_URL
    print(f"数据库: {url[:40]}...")
    if "sqlite" in url:
        migrate_sqlite(url)
    elif "mysql" in url:
        migrate_mysql(url)
    else:
        print(f"[ERROR] 不支持的数据库类型: {url}")
        sys.exit(1)