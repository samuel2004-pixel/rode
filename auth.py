"""
auth.py - session-based auth helpers for Flask
"""
import hashlib
from functools import wraps
from flask import session, redirect, url_for, flash, request
from db import get_db
import db as db_module


def hash_password(password: str):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def login_user(username, password):
    conn = get_db()
    try:
        user = db_module.get_user_by_username(conn, username)
        if not user:
            return False
        if int(user.get("is_active", 1)) == 0:
            flash("Account is disabled. Contact administrator.", "danger")
            return False
        if user.get("password_hash") != hash_password(password):
            flash("Invalid username or password.", "danger")
            return False
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]
        return True
    finally:
        conn.close()


def logout_user():
    session.clear()


def current_user():
    uid = session.get("user_id")
    return {
        "id": uid,
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role": session.get("role"),
        "is_authenticated": bool(uid),
        "is_admin": session.get("role") == "Admin",
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user().get("is_authenticated"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user.get("is_authenticated"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login_page"))
        if not user.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapper
