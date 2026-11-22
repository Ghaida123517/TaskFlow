import os
import sqlite3
import secrets
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from database import init_db

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "taskflow-local-development-only"
)

init_db()

# Sprint 2: allowed values for task status and priority
VALID_STATUSES = ("To Do", "In Progress", "Completed")
VALID_PRIORITIES = ("High", "Medium", "Low")


def parse_deadline(value):
    """Return (is_valid, deadline). An empty value means no deadline."""
    value = str(value or "").strip()

    if not value:
        return True, None

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False, None

    return True, value


def get_leader_task(conn, task_id):
    """Return the task only if it belongs to a team led by the logged-in user."""
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return None

    return conn.execute(
        """
        SELECT tasks.*
        FROM tasks
        JOIN teams ON tasks.team_id = teams.id
        WHERE tasks.id = ? AND teams.owner_id = ?
        """,
        (task_id, session["user_id"])
    ).fetchone()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    confirm = str(data.get("confirm_password", ""))

    if not name or not email or len(password) < 8:
        return jsonify({
            "success": False,
            "message": "Please enter valid information."
        }), 400

    if password != confirm:
        return jsonify({
            "success": False,
            "message": "Passwords do not match."
        }), 400

    hashed_password = generate_password_hash(password)

    conn = sqlite3.connect("taskflow.db")

    try:
        conn.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, hashed_password)
        )
        conn.commit()

    except sqlite3.IntegrityError:
        return jsonify({
            "success": False,
            "message": "This email is already registered."
        }), 409

    finally:
        conn.close()

    return jsonify({
        "success": True,
        "message": "Account created successfully!"
    }), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    conn.close()

    if user and check_password_hash(user["password"], password):
        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]

        return jsonify({
            "success": True,
            "message": "Login successful!"
        })

    return jsonify({
        "success": False,
        "message": "Invalid email or password."
    }), 401

# DASHBOARD
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("home"))

    # Get teams created by the logged-in user
    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    teams = conn.execute(
       """SELECT id, name, invite_code, owner_id
FROM teams
WHERE owner_id = ?
OR id IN (
    SELECT team_id FROM team_members WHERE user_id = ?
)""",
        (session["user_id"], session["user_id"])
    ).fetchall()


 # Get tasks belonging to teams led by this user
    tasks = conn.execute("""
        SELECT tasks.id, tasks.title, tasks.team_id
        FROM tasks
        JOIN teams ON tasks.team_id = teams.id
        WHERE teams.owner_id = ?
    """, (session["user_id"],)).fetchall()

    # Get members of teams led by this user
    members = conn.execute("""
        SELECT team_members.team_id, users.id, users.name
        FROM team_members
        JOIN users ON team_members.user_id = users.id
        JOIN teams ON team_members.team_id = teams.id
        WHERE teams.owner_id = ?
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        teams=teams,
        tasks=tasks,
        members=members
    )

# LOGOUT
@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out successfully!"
    })
# CREATE TEAM
@app.route("/create-team", methods=["POST"])
def create_team():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}
    team_name = str(data.get("name", "")).strip()

    if not team_name:
        return jsonify({
            "success": False,
            "message": "Please enter a team name."
        }), 400

    if len(team_name) > 100:
        return jsonify({
            "success": False,
            "message": "Team name is too long."
        }), 400

    invite_code = secrets.token_hex(4).upper()
    conn = sqlite3.connect("taskflow.db")

    cursor = conn.execute(
        "INSERT INTO teams (name, owner_id, invite_code) VALUES (?, ?, ?)",
        (team_name, session["user_id"], invite_code)
    )

    conn.commit()
    team_id = cursor.lastrowid
    conn.close()

    return jsonify({
        "success": True,
        "message": "Team created successfully!",
       "team_id": team_id,
"invite_code": invite_code
    }), 201


 # JOIN TEAM
@app.route("/join-team", methods=["POST"])
def join_team():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}
    invite_code = str(data.get("invite_code", "")).strip().upper()

    if not invite_code:
        return jsonify({
            "success": False,
            "message": "Please enter an invitation code."
        }), 400

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    team = conn.execute(
        "SELECT id, name, owner_id FROM teams WHERE invite_code = ?",
        (invite_code,)
    ).fetchone()

    if team is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Invalid invitation code."
        }), 404

    if team["owner_id"] == session["user_id"]:
        conn.close()
        return jsonify({
            "success": False,
            "message": "You are already the leader of this team."
        }), 400

    existing_member = conn.execute(
        "SELECT id FROM team_members WHERE team_id = ? AND user_id = ?",
        (team["id"], session["user_id"])
    ).fetchone()

    if existing_member:
        conn.close()
        return jsonify({
            "success": False,
            "message": "You are already a member of this team."
        }), 400

    conn.execute(
        "INSERT INTO team_members (team_id, user_id) VALUES (?, ?)",
        (team["id"], session["user_id"])
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "You have successfully joined the team!",
        "team_name": team["name"]
    }), 200
@app.route("/create-task", methods=["POST"])
def create_task():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}

    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    team_id = data.get("team_id")
    member_id = data.get("member_id")

    if not title:
        return jsonify({
            "success": False,
            "message": "Task title is required."
        }), 400

    # PB-13: priority level (High, Medium or Low)
    priority = str(data.get("priority") or "Medium").strip()

    if priority not in VALID_PRIORITIES:
        return jsonify({
            "success": False,
            "message": "Please choose High, Medium, or Low priority."
        }), 400

    # PB-12: optional deadline in YYYY-MM-DD format
    valid_deadline, deadline = parse_deadline(data.get("deadline"))

    if not valid_deadline:
        return jsonify({
            "success": False,
            "message": "Please enter a valid deadline date."
        }), 400

    try:
        team_id = int(team_id)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Please select a valid team."
        }), 400

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    team = conn.execute(
        "SELECT id FROM teams WHERE id = ? AND owner_id = ?",
        (team_id, session["user_id"])
    ).fetchone()

    if not team:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Only the team leader can create tasks."
        }), 403

    # PB-7: the selected member must belong to the selected team
    assigned_to = None

    if member_id not in (None, ""):
        try:
            member_id = int(member_id)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({
                "success": False,
                "message": "Please select a valid member."
            }), 400

        is_member = conn.execute(
            "SELECT id FROM team_members WHERE team_id = ? AND user_id = ?",
            (team_id, member_id)
        ).fetchone()

        if not is_member:
            conn.close()
            return jsonify({
                "success": False,
                "message": "The selected member does not belong to this team."
            }), 400

        assigned_to = member_id

    cursor = conn.execute(
    """INSERT INTO tasks
       (team_id, title, description, assigned_to, status, priority, deadline)
       VALUES (?, ?, ?, ?, 'To Do', ?, ?)""",
    (team_id, title, description, assigned_to, priority, deadline)
)

    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Task created successfully!",
        "task_id": task_id
    }), 201
@app.route("/my-tasks", methods=["GET"])
def my_tasks():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    # PB-14 filters (status / priority) and PB-17 keyword search
    status = request.args.get("status", "").strip()
    priority = request.args.get("priority", "").strip()
    keyword = request.args.get("q", "").strip()

    query = """
        SELECT tasks.id, tasks.team_id, tasks.title, tasks.description,
               tasks.status, tasks.priority, tasks.deadline,
               teams.name AS team_name
        FROM tasks
        JOIN teams ON tasks.team_id = teams.id
        WHERE tasks.assigned_to = ?
    """
    params = [session["user_id"]]

    if status in VALID_STATUSES:
        query += " AND tasks.status = ?"
        params.append(status)

    if priority in VALID_PRIORITIES:
        query += " AND tasks.priority = ?"
        params.append(priority)

    if keyword:
        query += " AND tasks.title LIKE ?"
        params.append("%" + keyword + "%")

    query += """
        ORDER BY
            CASE tasks.status WHEN 'Completed' THEN 1 ELSE 0 END,
            CASE tasks.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
            tasks.deadline IS NULL, tasks.deadline, tasks.id
    """

    tasks = conn.execute(query, params).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "tasks": [dict(task) for task in tasks]
    }), 200


# =========================================================
# SPRINT 2 FEATURES
# =========================================================

# PB-9: UPDATE THE STATUS OF AN ASSIGNED TASK
@app.route("/update-task-status", methods=["POST"])
def update_task_status():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()

    if status not in VALID_STATUSES:
        return jsonify({
            "success": False,
            "message": "Please choose To Do, In Progress, or Completed."
        }), 400

    try:
        task_id = int(data.get("task_id"))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "message": "Invalid task."
        }), 400

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    task = conn.execute(
        "SELECT id, assigned_to FROM tasks WHERE id = ?",
        (task_id,)
    ).fetchone()

    if task is None or task["assigned_to"] != session["user_id"]:
        conn.close()
        return jsonify({
            "success": False,
            "message": "You can only update tasks assigned to you."
        }), 403

    completed_at = (
        datetime.now().strftime("%Y-%m-%d %H:%M")
        if status == "Completed" else None
    )

    conn.execute(
        "UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
        (status, completed_at, task_id)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Task status updated to " + status + "."
    }), 200


# LEADER: LIST ALL TASKS OF THE TEAMS I LEAD (used by Manage Tasks)
@app.route("/team-tasks", methods=["GET"])
def team_tasks():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    tasks = conn.execute(
        """
        SELECT tasks.id, tasks.title, tasks.description, tasks.status,
               tasks.priority, tasks.deadline, tasks.team_id,
               teams.name AS team_name, users.name AS assignee
        FROM tasks
        JOIN teams ON tasks.team_id = teams.id
        LEFT JOIN users ON tasks.assigned_to = users.id
        WHERE teams.owner_id = ?
        ORDER BY teams.name, tasks.id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "tasks": [dict(task) for task in tasks]
    }), 200


# PB-10, PB-12, PB-13: EDIT TASK (title, description, deadline, priority)
@app.route("/edit-task", methods=["POST"])
def edit_task():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}

    title = str(data.get("title") or "").strip()
    description = str(data.get("description") or "").strip()
    priority = str(data.get("priority") or "Medium").strip()

    if not title:
        return jsonify({
            "success": False,
            "message": "Task title is required."
        }), 400

    if priority not in VALID_PRIORITIES:
        return jsonify({
            "success": False,
            "message": "Please choose High, Medium, or Low priority."
        }), 400

    valid_deadline, deadline = parse_deadline(data.get("deadline"))

    if not valid_deadline:
        return jsonify({
            "success": False,
            "message": "Please enter a valid deadline date."
        }), 400

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    task = get_leader_task(conn, data.get("task_id"))

    if task is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Only the team leader can edit this task."
        }), 403

    conn.execute(
        """
        UPDATE tasks
        SET title = ?, description = ?, priority = ?, deadline = ?
        WHERE id = ?
        """,
        (title, description, priority, deadline, task["id"])
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Task updated successfully!"
    }), 200


# PB-11: DELETE TASK
@app.route("/delete-task", methods=["POST"])
def delete_task():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    data = request.get_json(silent=True) or {}

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    task = get_leader_task(conn, data.get("task_id"))

    if task is None:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Only the team leader can delete this task."
        }), 403

    conn.execute("DELETE FROM tasks WHERE id = ?", (task["id"],))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Task deleted successfully!"
    }), 200


# PB-15: TEAM PROGRESS DASHBOARD
@app.route("/team-progress", methods=["GET"])
def team_progress():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT teams.id, teams.name,
            SUM(CASE WHEN tasks.status = 'To Do' THEN 1 ELSE 0 END) AS todo,
            SUM(CASE WHEN tasks.status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN tasks.status = 'Completed' THEN 1 ELSE 0 END) AS completed,
            COUNT(tasks.id) AS total
        FROM teams
        LEFT JOIN tasks ON tasks.team_id = teams.id
        WHERE teams.owner_id = ?
        GROUP BY teams.id, teams.name
        ORDER BY teams.name
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "teams": [dict(row) for row in rows]
    }), 200


# PB-18: COMPLETED TASKS HISTORY
@app.route("/completed-history", methods=["GET"])
def completed_history():
    if "user_id" not in session:
        return jsonify({
            "success": False,
            "message": "Please log in first."
        }), 401

    conn = sqlite3.connect("taskflow.db")
    conn.row_factory = sqlite3.Row

    tasks = conn.execute(
        """
        SELECT tasks.id, tasks.title, tasks.status, tasks.completed_at,
               teams.name AS team_name, users.name AS assignee
        FROM tasks
        JOIN teams ON tasks.team_id = teams.id
        LEFT JOIN users ON tasks.assigned_to = users.id
        WHERE teams.owner_id = ? AND tasks.status = 'Completed'
        ORDER BY tasks.completed_at DESC, tasks.id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "tasks": [dict(task) for task in tasks]
    }), 200


if __name__ == "__main__":
    app.run(debug=True) 