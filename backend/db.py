from contextlib import contextmanager
from pathlib import Path
import sqlite3

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path(__file__).resolve().parent.parent / "app.db"
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    migrate_sqlite()


def migrate_sqlite() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(personas)").fetchall()}
        migrations = [
            ("is_system", "INTEGER DEFAULT 0"),
            ("model_role", "TEXT DEFAULT 'chat_strong'"),
            ("model_override", "TEXT"),
            ("sim_config", "TEXT"),
        ]
        for name, definition in migrations:
            if name not in columns:
                conn.execute(f"ALTER TABLE personas ADD COLUMN {name} {definition}")
        if "is_steward" in columns:
            conn.execute("UPDATE personas SET is_system = 1 WHERE is_steward = 1")
        if "model" in columns:
            conn.execute(
                """
                UPDATE personas
                SET model_role = CASE
                    WHEN is_system = 1 THEN 'steward'
                    ELSE 'chat_strong'
                END
                WHERE model_role IS NULL OR model_role = ''
                """
            )
        table_migrations = {
            "channels": [
                ("is_system", "INTEGER DEFAULT 0"),
                ("pinned", "INTEGER"),
                ("archived", "INTEGER"),
                ("ai_enabled", "INTEGER DEFAULT 1"),
            ],
            "messages": [
                ("status", "TEXT DEFAULT 'delivered'"),
                ("chunk_group", "TEXT"),
                ("author_type", "TEXT DEFAULT 'human'"),
                ("author_user_id", "INTEGER"),
                ("ai_enabled_snapshot", "INTEGER DEFAULT 1"),
            ],
            "todos": [
                ("priority", "TEXT DEFAULT 'med'"),
                ("notes", "TEXT"),
                ("repeat_rule", "TEXT"),
                ("source", "TEXT DEFAULT 'steward'"),
            ],
            "persona_state": [
                ("last_interaction_at", "TEXT"),
                ("milestones", "TEXT DEFAULT '[]'"),
            ],
            "persona_card": [
                ("voice", "TEXT"),
                ("traits", "TEXT DEFAULT '[]'"),
            ],
        }
        for table, fields in table_migrations.items():
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in fields:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        migrate_channel_members(conn)
        conn.execute("UPDATE messages SET status = 'delivered' WHERE status IS NULL")
        conn.execute("UPDATE messages SET author_type = 'ai' WHERE sender = 'persona'")
        conn.execute("UPDATE messages SET author_type = 'human' WHERE sender = 'user'")
        conn.execute("UPDATE messages SET ai_enabled_snapshot = 1 WHERE ai_enabled_snapshot IS NULL")
        conn.execute("UPDATE channels SET ai_enabled = 1 WHERE ai_enabled IS NULL")
        conn.execute("UPDATE todos SET priority = 'med' WHERE priority IS NULL OR priority = ''")
        conn.execute("UPDATE todos SET source = 'steward' WHERE source IS NULL OR source = ''")
        conn.execute(
            """
            UPDATE persona_state
            SET last_interaction_at = last_interaction
            WHERE (last_interaction_at IS NULL OR last_interaction_at = '')
              AND last_interaction IS NOT NULL
            """
        )
        conn.execute(
            "UPDATE persona_state SET milestones = '[]' WHERE milestones IS NULL OR milestones = ''"
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys=ON")


def migrate_channel_members(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(channel_members)").fetchall()}
    if not columns:
        return
    if "id" in columns and "member_type" in columns and "user_id" in columns:
        conn.execute(
            "UPDATE channel_members SET member_type = 'persona' WHERE member_type IS NULL OR member_type = ''"
        )
        return

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_members_new (
            id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            member_type TEXT DEFAULT 'persona',
            persona_id INTEGER,
            user_id INTEGER
        )
        """
    )
    select_persona = "persona_id" if "persona_id" in columns else "NULL"
    conn.execute(
        f"""
        INSERT INTO channel_members_new (channel_id, member_type, persona_id, user_id)
        SELECT channel_id, 'persona', {select_persona}, NULL
        FROM channel_members
        """
    )
    conn.execute("DROP TABLE channel_members")
    conn.execute("ALTER TABLE channel_members_new RENAME TO channel_members")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_channel_members_channel_id ON channel_members(channel_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_channel_members_member_type ON channel_members(member_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_channel_members_persona_id ON channel_members(persona_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_channel_members_user_id ON channel_members(user_id)")


@contextmanager
def session_scope():
    with Session(engine) as session:
        yield session
