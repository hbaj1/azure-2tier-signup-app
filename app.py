import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from mysql.connector import Error
import bcrypt

app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY", "dev-secret-change-me")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", ""),
    "user": os.environ.get("DB_USER", ""),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "appdb"),
    "port": int(os.environ.get("DB_PORT", 3306)),
}


def get_db_connection():
    if not DB_CONFIG["host"]:
        return None
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        app.logger.error(f"DB connection failed: {e}")
        return None


@app.route("/")
def home():
    return render_template("home.html", db_configured=bool(DB_CONFIG["host"]))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not username or not email or not password:
        flash("All fields are required.")
        return redirect(url_for("signup"))

    conn = get_db_connection()
    if conn is None:
        flash("Database is not connected yet. UI works, but signup can't be saved.")
        return redirect(url_for("signup"))

    try:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, hashed.decode("utf-8")),
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash("Account created. Please log in.")
        return redirect(url_for("login"))
    except Error as e:
        flash(f"Signup failed: {e}")
        return redirect(url_for("signup"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    conn = get_db_connection()
    if conn is None:
        flash("Database is not connected yet. UI works, but login can't be verified.")
        return redirect(url_for("login"))

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.")
            return redirect(url_for("login"))
    except Error as e:
        flash(f"Login failed: {e}")
        return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session["username"])


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/healthz")
def healthz():
    return {"status": "ok", "db_connected": get_db_connection() is not None}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)