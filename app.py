import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    cash = db.execute("SELECT cash FROM users WHERE id =?", session["user_id"])[0]["cash"]
    owned = db.execute("SELECT symbol, shares FROM owned WHERE id=?", session["user_id"])
    for holding in owned:
        price = lookup(holding["symbol"])["price"]
        holding["price"] = price
        holding["total"] = price * holding["shares"]
    sum = 0
    for holding in owned:
        sum += holding["price"] * holding["shares"]
    sum += cash
    return render_template("index.html", cash=cash, owned=owned, sum=sum)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        ptime = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
        symbol = request.form.get("symbol")
        try:
            shares = float(request.form.get("shares"))
        except Exception:
            return apology("Integer value required")
        if not symbol or lookup(symbol) is None:
            return apology("Input blank or symbol does not exist")
        if not shares % 1 < 0.00001 or shares < 1:
            return apology("Positive integer number of shares required")
        cost = float(lookup(symbol)["price"])
        funds = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        if (shares * cost) > funds[0]["cash"]:
            return apology("You do not have sufficient funds")
        db.execute("UPDATE users SET cash = ? WHERE id = ?", (funds[0]["cash"] - (shares * cost)), session["user_id"])
        db.execute("INSERT INTO purchases (datetime, id, symbol, shares, price) VALUES(?,?,?,?,?)", ptime, session["user_id"], symbol, shares, cost)
        if len(db.execute("SELECT * FROM owned WHERE id = ? AND symbol = ?", session["user_id"], symbol)) == 0:
            db.execute("INSERT INTO owned (id, symbol, shares) VALUES(?,?,?)", session["user_id"], symbol, shares)
        else:
            owned_shares = db.execute("SELECT shares FROM owned WHERE id = ? AND symbol = ?", session["user_id"], symbol)[0]["shares"]
            db.execute("UPDATE owned SET shares = ? WHERE id = ? AND symbol = ?", owned_shares + shares, session["user_id"], symbol)
        return redirect("/")


@app.route("/history")
@login_required
def history():
    transactions = db.execute("SELECT datetime, symbol, shares, price FROM purchases WHERE id = ?", session["user_id"])
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        quotes = lookup(request.form.get("symbol"))
        if quotes is None:
            return apology("Invalid ticker", 400)
        return render_template("quoted.html", quotes=quotes)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if not username:
            return apology("must provide username", 400)
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) != 0:
            return apology("Username already exists", 400)
        if not password or not confirmation or password != confirmation:
            return apology("Passwords do not match", 400)
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, generate_password_hash(password))
        return redirect("/")
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    owned = db.execute("SELECT symbol, shares FROM owned WHERE id =?", session["user_id"])
    if request.method == "GET":
        return render_template("sell.html", owned=owned)
    else:
        shares = float(request.form.get("shares"))
        symbol = request.form.get("symbol")
        if symbol == "None":
            return apology("Stock must be selected")
        if not shares % 1 < 0.00001 or shares < 1:
            return apology("Positive integer number of shares required")
        shares = int(shares)
        if shares > db.execute("SELECT shares FROM owned WHERE id=? AND symbol=?", session["user_id"], symbol)[0]["shares"]:
            return apology("You do not own enough shares")
        else:
            ptime = datetime.now().strftime("%m/%d/%Y, %H:%M:%S")
            cost = float(lookup(symbol)["price"])
            funds = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
            db.execute("UPDATE users SET cash = ? WHERE id = ?", (funds[0]["cash"] + (shares * cost)), session["user_id"])
            db.execute("INSERT INTO purchases (datetime, id, symbol, shares, price) VALUES(?,?,?,?,?)", ptime, session["user_id"], symbol, shares*-1, cost)
            owned_shares = db.execute("SELECT shares FROM owned WHERE id = ? AND symbol = ?", session["user_id"], symbol)[0]["shares"]
            if owned_shares - shares < 0.001:
                db.execute("DELETE FROM owned WHERE id = ? AND symbol = ?", session["user_id"], symbol)
            else:
                db.execute("UPDATE owned SET shares = ? WHERE id = ? AND symbol = ?", owned_shares - shares, session["user_id"], symbol)
            return redirect("/")
