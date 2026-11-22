"""Create, rename or reset the TaskFlow team accounts.

Run from the project folder:  py seed_users.py
Every account below gets the password 12345678.
Old test emails are renamed to the new ones, so teams and tasks are kept.
"""
import sqlite3
from werkzeug.security import generate_password_hash
from database import init_db

PASSWORD = "12345678"

# (name, email, old emails that belong to the same person)
ACCOUNTS = [
    ("Ghaida", "ghaida@email.com", ["ghydayan@gmail.com"]),
    ("Ghala", "ghala@email.com", ["gghh@gmail.com"]),
    ("Lina", "lina@email.com", ["ggghhh@gmail.com"]),
    ("Rama", "rama@email.com", ["rama@taskflow.com"]),
    ("Jory", "jory@email.com", ["jory@taskflow.com"]),
]


def seed():
    init_db()
    conn = sqlite3.connect("taskflow.db")

    for name, email, old_emails in ACCOUNTS:
        hashed = generate_password_hash(PASSWORD)
        user = None

        for address in [email] + old_emails:
            user = conn.execute("SELECT id FROM users WHERE email = ?", (address,)).fetchone()
            if user:
                break

        if user:
            conn.execute(
                "UPDATE users SET name = ?, email = ?, password = ? WHERE id = ?",
                (name, email, hashed, user[0])
            )
            print(f"Updated: {name} <{email}>")
        else:
            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, hashed)
            )
            print(f"Created: {name} <{email}>")

    conn.commit()
    conn.close()
    print(f"Done. Password for all accounts: {PASSWORD}")


if __name__ == "__main__":
    seed()
