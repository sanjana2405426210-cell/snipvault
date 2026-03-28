from flask import Flask, render_template, request, redirect, session
from flask_bcrypt import Bcrypt
from functools import wraps
import mysql.connector
import re
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "snipvault_dev_secret")
bcrypt = Bcrypt(app)

# ---------- MYSQL CONNECTION ----------
def get_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "snipvault_db")
    )

# ---------- STOP WORDS ----------
stop_words = {
    "the","is","in","and","a","to","for","of","on","with",
    "as","by","this","that","it","an","be"
}

# ---------- TOKENIZE ----------
def tokenize(text):
    text = text.lower()
    words = re.findall(r'\b\w+\b', text)
    filtered = [w for w in words if w not in stop_words and len(w) > 2]
    return filtered

# ---------- BUILD INDEX ----------
def build_index(snippet_id, text):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM inverted_index WHERE snippet_id=%s", (snippet_id,))
    words = tokenize(text)
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    for word, count in freq.items():
        cur.execute(
            "INSERT INTO inverted_index(word,snippet_id,frequency) VALUES(%s,%s,%s)",
            (word, snippet_id, count)
        )
    db.commit()
    db.close()

# ---------- LOGIN REQUIRED ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username=%s", (u,))
        user = cur.fetchone()
        db.close()
        if user and bcrypt.check_password_hash(user[2], p):
            session["user"] = u
            return redirect("/dashboard")
        else:
            error = "Invalid username or password."
    return render_template("login.html", error=error)

# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if len(p) < 6:
            error = "Password must be at least 6 characters."
            return render_template("register.html", error=error)
        hashed = bcrypt.generate_password_hash(p).decode("utf-8")
        db = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO users(username,password) VALUES(%s,%s)", (u, hashed))
            db.commit()
            db.close()
            return redirect("/")
        except Exception:
            db.close()
            error = "Username already taken. Please choose another."
    return render_template("register.html", error=error)

# ---------- DASHBOARD ----------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM snippets ORDER BY id DESC")
    data = cur.fetchall()
    db.close()
    return render_template("dashboard.html", snippets=data)

# ---------- ADD SNIPPET ----------
@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        title = request.form["title"]
        code = request.form["code"]
        lang = request.form["language"]
        desc = request.form["description"]
        db = get_db()
        cur = db.cursor()
        cur.execute("""
        INSERT INTO snippets(title,code,language,description,is_favorite)
        VALUES(%s,%s,%s,%s,0)
        """, (title, code, lang, desc))
        db.commit()
        snippet_id = cur.lastrowid
        full_text = title + " " + desc
        build_index(snippet_id, full_text)
        db.close()
        return redirect("/dashboard")
    return render_template("add_snippet.html")

# ---------- INVERTED INDEX SEARCH ----------
@app.route("/keyword")
@login_required
def keyword():
    query = request.args.get("q", "")
    if not query:
        return redirect("/dashboard")
    words = tokenize(query)
    db = get_db()
    cur = db.cursor()
    snippet_sets = []
    for word in words:
        cur.execute("SELECT snippet_id FROM inverted_index WHERE word=%s", (word,))
        ids = cur.fetchall()
        snippet_sets.append(set([i[0] for i in ids]))
    if not snippet_sets:
        db.close()
        return render_template("dashboard.html", snippets=[])
    final_ids = set.intersection(*snippet_sets)
    if not final_ids:
        db.close()
        return render_template("dashboard.html", snippets=[])
    format_ids = ",".join(str(i) for i in final_ids)
    cur.execute(f"SELECT * FROM snippets WHERE id IN ({format_ids})")
    results = cur.fetchall()
    db.close()
    return render_template("dashboard.html", snippets=results)

# ---------- FILTER LANGUAGE ----------
@app.route("/filter/<lang>")
@login_required
def filter_lang(lang):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM snippets WHERE language=%s ORDER BY id DESC", (lang,))
    data = cur.fetchall()
    db.close()
    return render_template("dashboard.html", snippets=data)

# ---------- FAVORITE ----------
@app.route("/fav/<int:id>")
@login_required
def fav(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT is_favorite FROM snippets WHERE id=%s", (id,))
    row = cur.fetchone()
    if row:
        new_val = 0 if row[0] else 1
        cur.execute("UPDATE snippets SET is_favorite=%s WHERE id=%s", (new_val, id))
        db.commit()
    db.close()
    return redirect("/dashboard")

# ---------- EDIT SNIPPET ----------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_snippet(id):
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        title = request.form["title"]
        code = request.form["code"]
        lang = request.form["language"]
        desc = request.form["description"]
        cur.execute("""
            UPDATE snippets SET title=%s, code=%s, language=%s, description=%s
            WHERE id=%s
        """, (title, code, lang, desc, id))
        db.commit()
        full_text = title + " " + desc
        build_index(id, full_text)
        db.close()
        return redirect("/dashboard")
    cur.execute("SELECT * FROM snippets WHERE id=%s", (id,))
    snippet = cur.fetchone()
    db.close()
    return render_template("edit_snippet.html", snippet=snippet)

# ---------- DELETE SNIPPET ----------
@app.route("/delete/<int:id>")
@login_required
def delete_snippet(id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM snippets WHERE id=%s", (id,))
    cur.execute("DELETE FROM inverted_index WHERE snippet_id=%s", (id,))
    db.commit()
    db.close()
    return redirect("/dashboard")

# ---------- FAVORITES PAGE ----------
@app.route("/favorites")
@login_required
def favorites():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM snippets WHERE is_favorite=1 ORDER BY id DESC")
    data = cur.fetchall()
    db.close()
    return render_template("dashboard.html", snippets=data)

# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------- RUN SERVER ----------
if __name__ == "__main__":
    app.run(debug=False)
