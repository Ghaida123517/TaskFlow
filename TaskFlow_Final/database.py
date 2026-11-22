import sqlite3

def init_db():
    conn = sqlite3.connect("taskflow.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL,
            invite_code TEXT UNIQUE,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            UNIQUE(team_id, user_id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            assigned_to INTEGER,
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (assigned_to) REFERENCES users(id)
        )
    """)

    # Sprint 2: add status, priority, deadline and completion date to tasks
    # (ALTER TABLE keeps every existing task and its data)
    existing_columns = [
        row[1] for row in cursor.execute("PRAGMA table_info(tasks)")
    ]

    if "status" not in existing_columns:
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'To Do'"
        )

    if "priority" not in existing_columns:
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'Medium'"
        )

    if "deadline" not in existing_columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT")

    if "completed_at" not in existing_columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")


    conn.commit()
    conn.close()