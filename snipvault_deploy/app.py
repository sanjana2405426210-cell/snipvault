from flask import Flask, render_template, request, redirect, session, flash, Response
from flask_bcrypt import Bcrypt
from functools import wraps
import mysql.connector
import re
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "snipvault_dev_secret")
bcrypt = Bcrypt(app)

# ---------- DATABASE HELPER ----------
def get_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "sanjana@1028"),
        database=os.environ.get("DB_NAME", "snipvault_db")
    )

# ---------- UTILITIES ----------
stop_words = {"the","is","in","and","a","to","for","of","on","with","as","by","this","it"}

def tokenize(text):
    text = text.lower()
    words = re.findall(r'\b\w+\b', text)
    return [w for w in words if w not in stop_words and len(w) > 2]

def build_index(snippet_id, text):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM inverted_index WHERE snippet_id=%s", (snippet_id,))
    words = tokenize(text)
    freq = {w: words.count(w) for w in set(words)}
    for word, count in freq.items():
        cur.execute("INSERT INTO inverted_index(word,snippet_id,frequency) VALUES(%s,%s,%s)", (word, snippet_id, count))
    db.commit()
    db.close()

# ---------- AUTH DECORATOR ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated

# ---------- ROUTES ----------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        db = get_db()
        cur = db.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s", (u,))
        user = cur.fetchone()
        db.close()
        if user and bcrypt.check_password_hash(user['password'], p):
            session["user_id"] = user['id']
            session["user_name"] = user['username']
            return redirect("/dashboard")
        flash("Invalid credentials")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        hashed = bcrypt.generate_password_hash(p).decode("utf-8")
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO users(username,password) VALUES(%s,%s)", (u, hashed))
            db.commit()
            return redirect("/")
        except:
            flash("Username taken")
        finally:
            db.close()
    return render_template("register.html")

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cur = db.cursor(dictionary=True)
    # Feature: User Isolation (Only see YOUR snippets)
    cur.execute("SELECT * FROM snippets WHERE user_id=%s ORDER BY id DESC", (session["user_id"],))
    data = cur.fetchall()
    db.close()
    return render_template("dashboard.html", snippets=data)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        title = request.form["title"]
        code = request.form["code"]
        lang = request.form["language"]
        desc = request.form["description"]
        is_pub = 1 if request.form.get("is_public") else 0
        
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO snippets(title,code,language,description,is_favorite,user_id,is_public)
            VALUES(%s,%s,%s,%s,0,%s,%s)
        """, (title, code, lang, desc, session["user_id"], is_pub))
        db.commit()
        snippet_id = cur.lastrowid
        build_index(snippet_id, f"{title} {desc}")
        db.close()
        return redirect("/dashboard")
    return render_template("add_snippet.html")

@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_snippet(id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    
    # Security: Ensure user owns the snippet before editing
    cur.execute("SELECT * FROM snippets WHERE id=%s AND user_id=%s", (id, session["user_id"]))
    snippet = cur.fetchone()
    
    if not snippet:
        return "Unauthorized", 403

    if request.method == "POST":
        # FIXED: Variables defined and used strictly inside the POST block
        new_title = request.form["title"]
        new_code = request.form["code"]
        new_lang = request.form["language"]
        new_desc = request.form["description"]
        new_pub = 1 if request.form.get("is_public") else 0

        # Feature: Save current code to history before updating
        if snippet['code'] != new_code:
            cur.execute("INSERT INTO snippet_versions(snippet_id, code) VALUES(%s, %s)", (id, snippet['code']))

        cur.execute("""
            UPDATE snippets SET title=%s, code=%s, language=%s, description=%s, is_public=%s
            WHERE id=%s
        """, (new_title, new_code, new_lang, new_desc, new_pub, id))
        
        db.commit()
        build_index(id, f"{new_title} {new_desc}")
        db.close()
        return redirect("/dashboard")

    db.close()
    return render_template("edit_snippet.html", snippet=snippet)

# Feature: Public Feed (Community Snippets)
@app.route("/explore")
def explore():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM snippets WHERE is_public=1 ORDER BY id DESC")
    data = cur.fetchall()
    db.close()
    return render_template("dashboard.html", snippets=data, view_title="Public Explore")

# Feature: Export Snippet as File
@app.route("/download/<int:id>")
@login_required
def download_snippet(id):
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM snippets WHERE id=%s", (id,))
    s = cur.fetchone()
    db.close()
    
    file_ext = {"python": "py", "javascript": "js", "sql": "sql", "html": "html"}.get(s['language'].lower(), "txt")
    return Response(
        s['code'],
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename=snippet_{id}.{file_ext}"}
    )

@app.route("/delete/<int:id>")
@login_required
def delete_snippet(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM snippets WHERE id=%s AND user_id=%s", (id, session["user_id"]))
    db.commit()
    db.close()
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)