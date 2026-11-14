"""User login module: salted PBKDF2 password hashing, roles, and brute-force lockout (stdlib only)."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time

from backend.db import get_connection

ITERATIONS = 200_000
MAX_FAILS = 5
LOCK_SECONDS = 300
ROLES = ["admin", "analyst", "viewer"]
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


def init_users():
    with get_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'analyst',
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login TEXT)""")


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


def password_problem(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return "Password must contain at least one letter and one number."
    return None


def register(username: str, full_name: str, password: str, confirm: str):
    """Returns (ok, message). The very first account becomes admin."""
    username, full_name = username.strip(), full_name.strip()
    if not USERNAME_RE.match(username):
        return False, "Username must be 3-30 characters: letters, numbers, . _ -"
    if not full_name:
        return False, "Please enter your name."
    if password != confirm:
        return False, "Passwords do not match."
    problem = password_problem(password)
    if problem:
        return False, problem
    salt = os.urandom(16)
    with get_connection() as conn:
        first = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        try:
            conn.execute("INSERT INTO users (username, full_name, password_hash, salt, role) VALUES (?,?,?,?,?)",
                         (username, full_name, _hash(password, salt), salt.hex(), "admin" if first else "analyst"))
        except Exception:
            return False, "That username is already taken."
    return True, "Account created as admin. You can sign in now." if first else "Account created. You can sign in now."


def login(username: str, password: str):
    """Returns (user_dict | None, message)."""
    generic = "Incorrect username or password."
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username.strip(),)).fetchone()
        if row is None:
            _hash(password, b"0" * 16)  # keep timing similar
            return None, generic
        if row["locked_until"] > time.time():
            mins = int((row["locked_until"] - time.time()) // 60) + 1
            return None, f"Too many failed attempts. Try again in about {mins} minute(s)."
        ok = hmac.compare_digest(_hash(password, bytes.fromhex(row["salt"])), row["password_hash"])
        if not ok:
            fails = row["failed_attempts"] + 1
            lock = time.time() + LOCK_SECONDS if fails >= MAX_FAILS else 0
            conn.execute("UPDATE users SET failed_attempts=?, locked_until=? WHERE user_id=?",
                         (0 if lock else fails, lock, row["user_id"]))
            return None, generic
        conn.execute("UPDATE users SET failed_attempts=0, locked_until=0, last_login=CURRENT_TIMESTAMP WHERE user_id=?",
                     (row["user_id"],))
    return {"user_id": row["user_id"], "username": row["username"],
            "full_name": row["full_name"], "role": row["role"]}, "Welcome back!"


def list_users():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT user_id, username, full_name, role, created_at, last_login FROM users ORDER BY user_id")]


def set_role(user_id: int, role: str):
    if role not in ROLES:
        return False, "Invalid role."
    with get_connection() as conn:
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        cur = conn.execute("SELECT role FROM users WHERE user_id=?", (user_id,)).fetchone()
        if cur and cur["role"] == "admin" and role != "admin" and admins <= 1:
            return False, "There must be at least one admin."
        conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
    return True, "Role updated."


def delete_user(user_id: int):
    with get_connection() as conn:
        cur = conn.execute("SELECT role FROM users WHERE user_id=?", (user_id,)).fetchone()
        if cur and cur["role"] == "admin" and conn.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
            return False, "You can't delete the only admin."
        conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    return True, "User deleted."


def change_password(user_id: int, old: str, new: str):
    problem = password_problem(new)
    if problem:
        return False, problem
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or not hmac.compare_digest(_hash(old, bytes.fromhex(row["salt"])), row["password_hash"]):
            return False, "Current password is incorrect."
        salt = os.urandom(16)
        conn.execute("UPDATE users SET password_hash=?, salt=? WHERE user_id=?",
                     (_hash(new, salt), salt.hex(), user_id))
    return True, "Password changed."