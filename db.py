import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "workbench.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            source_lang     TEXT NOT NULL DEFAULT 'en',
            source_text     TEXT NOT NULL,
            current_stage   INTEGER NOT NULL DEFAULT 1,
            status          TEXT NOT NULL DEFAULT 'in_progress',
            governor_model  TEXT NOT NULL DEFAULT 'single',
            governor_a      TEXT,
            governor_b      TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stage_outputs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            stage       INTEGER NOT NULL,
            input_text  TEXT NOT NULL,
            output_text TEXT NOT NULL,
            operator    TEXT NOT NULL,
            model_used  TEXT,
            prompt_used TEXT,
            human_notes TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            action      TEXT NOT NULL,
            details     TEXT,
            created_at  TEXT NOT NULL
        );
    """)
    conn.commit()
    # Migrate Phase 1 databases that lack new columns
    _migrate_db(conn)
    conn.close()


def _migrate_db(conn):
    cursor = conn.execute("PRAGMA table_info(documents)")
    columns = [row[1] for row in cursor.fetchall()]
    migrations = {
        "governor_model": "ALTER TABLE documents ADD COLUMN governor_model TEXT NOT NULL DEFAULT 'single'",
        "governor_a": "ALTER TABLE documents ADD COLUMN governor_a TEXT",
        "governor_b": "ALTER TABLE documents ADD COLUMN governor_b TEXT",
    }
    for col, sql in migrations.items():
        if col not in columns:
            conn.execute(sql)
    conn.commit()


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_document(title, source_text, source_lang="en", governor_model="single", governor_a=None, governor_b=None):
    conn = get_conn()
    now = _now()
    cursor = conn.execute(
        "INSERT INTO documents (title, source_text, source_lang, current_stage, status, governor_model, governor_a, governor_b, created_at, updated_at) VALUES (?, ?, ?, 1, 'in_progress', ?, ?, ?, ?, ?)",
        (title, source_text, source_lang, governor_model, governor_a, governor_b, now, now),
    )
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_document(doc_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def get_all_documents():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_documents_for_user(name, role):
    if role == "coordinator":
        return get_all_documents()
    if role == "terminology_specialist" or role == "final_reviewer":
        return get_all_documents()
    # Governor: show docs where they are governor_a or governor_b
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM documents WHERE governor_a = ? OR governor_b = ? ORDER BY updated_at DESC",
        (name, name),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stage_outputs(doc_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM stage_outputs WHERE document_id = ? ORDER BY stage",
        (doc_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_stage_output(doc_id, stage, input_text, output_text, operator, model_used=None, prompt_used=None, human_notes=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO stage_outputs (document_id, stage, input_text, output_text, operator, model_used, prompt_used, human_notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (doc_id, stage, input_text, output_text, operator, model_used, prompt_used, human_notes, _now()),
    )
    conn.commit()
    conn.close()


def update_document_stage(doc_id, stage, status=None):
    conn = get_conn()
    if status:
        conn.execute(
            "UPDATE documents SET current_stage = ?, status = ?, updated_at = ? WHERE id = ?",
            (stage, status, _now(), doc_id),
        )
    else:
        conn.execute(
            "UPDATE documents SET current_stage = ?, updated_at = ? WHERE id = ?",
            (stage, _now(), doc_id),
        )
    conn.commit()
    conn.close()


def log_audit(doc_id, action, details=None):
    conn = get_conn()
    details_str = json.dumps(details, ensure_ascii=False) if details else None
    conn.execute(
        "INSERT INTO audit_log (document_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (doc_id, action, details_str, _now()),
    )
    conn.commit()
    conn.close()


def get_audit_log(doc_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE document_id = ? ORDER BY created_at",
        (doc_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
