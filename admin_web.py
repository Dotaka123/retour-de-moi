import os
import json
import secrets
import functools
import urllib.request
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from dotenv import load_dotenv

import database as db

load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "kaonty2024")
BOT_NAME = os.getenv("BOT_NAME", "Kaonty Store")
BINANCE_EMAIL = os.getenv("BINANCE_EMAIL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")


def send_telegram_message(chat_id, text, parse_mode=None):
    if not BOT_TOKEN or not chat_id:
        return False
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        # Retry without parse_mode
        payload.pop("parse_mode", None)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception:
            return False


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Logged in successfully!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid password!", "error")
    return render_template("login.html", bot_name=BOT_NAME)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@app.route("/")
@admin_required
def dashboard():
    users = db.get_all_users()
    orders = db.get_all_orders()
    topups = db.get_pending_topups()
    total_balance = sum(u["balance"] for u in users)
    total_revenue = sum(o["total_cost"] for o in orders)
    total_topup_pending = sum(t["amount"] for t in topups)
    return render_template(
        "dashboard.html", bot_name=BOT_NAME,
        user_count=len(users), order_count=len(orders),
        total_balance=total_balance, total_revenue=total_revenue,
        pending_topups=len(topups), pending_topup_amount=total_topup_pending,
    )


@app.route("/users")
@admin_required
def users():
    all_users = db.get_all_users()
    search = request.args.get("search", "").strip()
    if search:
        all_users = [
            u for u in all_users
            if search.lower() in str(u["telegram_id"])
            or search.lower() in (u.get("username") or "").lower()
            or search.lower() in (u.get("first_name") or "").lower()
        ]
    return render_template("users.html", bot_name=BOT_NAME, users=all_users, search=search)


@app.route("/users/<int:telegram_id>/ban", methods=["POST"])
@admin_required
def ban_user_route(telegram_id):
    db.ban_user(telegram_id)
    flash("User " + str(telegram_id) + " has been banned.", "success")
    return redirect(url_for("users"))


@app.route("/users/<int:telegram_id>/unban", methods=["POST"])
@admin_required
def unban_user_route(telegram_id):
    db.unban_user(telegram_id)
    flash("User " + str(telegram_id) + " has been unbanned.", "success")
    return redirect(url_for("users"))


@app.route("/users/<int:telegram_id>/set-balance", methods=["POST"])
@admin_required
def set_balance_route(telegram_id):
    try:
        amount = float(request.form.get("amount", 0))
        db.set_balance(telegram_id, amount)
        flash("Balance set to $" + "{:,.2f}".format(amount) + " for user " + str(telegram_id) + ".", "success")
    except (ValueError, TypeError):
        flash("Invalid amount.", "error")
    return redirect(url_for("users"))


@app.route("/orders")
@admin_required
def orders():
    all_orders = db.get_all_orders(limit=100)
    return render_template("orders.html", bot_name=BOT_NAME, orders=all_orders)


@app.route("/topups")
@admin_required
def topups():
    pending = db.get_pending_topups()
    return render_template("topups.html", bot_name=BOT_NAME, topups=pending)


@app.route("/topups/<int:topup_id>/approve", methods=["POST"])
@admin_required
def approve_topup_route(topup_id):
    topup = db.approve_topup(topup_id)
    if topup:
        msg = "\u2705 Topup Approved!\n\n"
        msg += "Your balance has been credited with $" + "{:,.2f}".format(float(topup["amount"])) + "\n"
        msg += "Use /balance to check your new balance."
        send_telegram_message(topup["user_id"], msg)
        flash("Topup of $" + "{:,.2f}".format(float(topup["amount"])) + " approved for user " + str(topup["user_id"]) + ".", "success")
    else:
        flash("Failed to approve topup.", "error")
    return redirect(url_for("topups"))


@app.route("/topups/<int:topup_id>/reject", methods=["POST"])
@admin_required
def reject_topup_route(topup_id):
    topup_info = None
    try:
        conn = db.get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM " + db.T_TOPUPS + " WHERE id = %s", (topup_id,))
            topup_info = cur.fetchone()
        db.return_db(conn)
    except Exception:
        pass

    if db.reject_topup(topup_id):
        if topup_info:
            msg = "\u274c Topup Rejected\n\n"
            msg += "Your topup request of $" + "{:,.2f}".format(float(topup_info["amount"])) + " has been rejected.\n"
            msg += "Contact support if you believe this is an error."
            send_telegram_message(topup_info["user_id"], msg)
        flash("Topup rejected.", "success")
    else:
        flash("Failed to reject topup.", "error")
    return redirect(url_for("topups"))


@app.route("/broadcast", methods=["GET", "POST"])
@admin_required
def broadcast():
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if not message:
            flash("Message cannot be empty.", "error")
            return redirect(url_for("broadcast"))
        users = db.get_all_users()
        sent = 0
        for u in users:
            result = send_telegram_message(u["telegram_id"], message)
            if result:
                sent += 1
        flash("Broadcast sent to " + str(sent) + "/" + str(len(users)) + " users.", "success")
        return redirect(url_for("dashboard"))
    return render_template("broadcast.html", bot_name=BOT_NAME)


def run_web_admin(port=5000):
    db.init_db()
    print("Admin panel running at http://localhost:" + str(port))
    print("Password: " + ADMIN_PASSWORD)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run_web_admin()
