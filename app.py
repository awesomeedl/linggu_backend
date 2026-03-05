from flask import Flask, render_template, jsonify, request
import sqlite3
import datetime
import random

app = Flask(__name__)
DB_PATH = "poems.db"


def get_daily_poem():
    """Return a poem chosen pseudorandomly but deterministically for the current day."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM poems")
    total = c.fetchone()[0]
    if total == 0:
        conn.close()
        return None

    # seed with current date so it changes every day
    today = datetime.date.today().isoformat()
    rng = random.Random(today)
    index = rng.randrange(total)
    c.execute(
        "SELECT id, title, author, dynasty, text FROM poems LIMIT 1 OFFSET ?",
        (index,)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "title": row[1],
            "author": row[2],
            "dynasty": row[3],
            "text": row[4],
        }
    return None


@app.route("/")
def index():
    # initial page loads htmx container that will request the daily poem
    return render_template("index.html")


@app.route("/daily")
def daily_view():
    # Returns just the daily poem view fragment (without full layout)
    return render_template("_daily_view.html")


@app.route("/poem")
def poem_fragment():
    poem = get_daily_poem()
    return render_template("_poem.html", poem=poem)


@app.route("/poem/<int:poem_id>")
def poem_by_id(poem_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, title, author, dynasty, text FROM poems WHERE id = ?",
        (poem_id,)
    )
    row = c.fetchone()
    conn.close()
    if row:
        poem = {
            "id": row[0],
            "title": row[1],
            "author": row[2],
            "dynasty": row[3],
            "text": row[4],
        }
    else:
        poem = None
    return render_template("_poem.html", poem=poem)


@app.route("/api/poem")
def poem_json():
    poem = get_daily_poem()
    return jsonify(poem)


@app.route("/search")
def search():
    import flask
    q = flask.request.args.get("q", "").strip()
    results = []
    if q:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT poems.id, poems.title, poems.author, poems.dynasty, poems.text FROM poems \
             JOIN poem_fts ON poems.rowid = poem_fts.rowid \
             WHERE poem_fts MATCH ? LIMIT 50",
            (q,)
        )
        for r in c.fetchall():
            text = r[4] or ""
            words = text.split()
            preview = (" ".join(words[:50]) + "...") if len(words) > 50 else text
            results.append({
                "id": r[0],
                "title": r[1],
                "author": r[2],
                "dynasty": r[3],
                "text_preview": preview,
            })
        conn.close()
    return render_template("_search_results.html", results=results, q=q)


@app.route("/dynasties")
def dynasties():
    # return dynasties with their authors for sidebar tree
    # accept optional query params to know which dynasty/author is selected
    selected_dynasty = request.args.get("dynasty", "").strip()
    selected_author = request.args.get("author", "").strip()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dynasty, author FROM poems WHERE dynasty IS NOT NULL AND author IS NOT NULL GROUP BY dynasty, author ORDER BY dynasty, author")
    rows = c.fetchall()
    conn.close()
    dyn_map = {}
    for dyn, auth in rows:
        if not dyn:
            continue
        dyn_map.setdefault(dyn, []).append(auth or "")
    # authors list may contain duplicates but group by ensures unique pairs
    return render_template("_dynasties.html", dynasties=dyn_map,
                           selected_dynasty=selected_dynasty,
                           selected_author=selected_author)


@app.route("/poems")
def poems_list():
    dynasty = request.args.get("dynasty", "").strip()
    author = request.args.get("author", "").strip()
    page = request.args.get("page", "1")
    try:
        page = int(page)
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1
    
    per_page = 10
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # build conditions
    conditions = []
    params = []
    if dynasty:
        conditions.append("dynasty = ?")
        params.append(dynasty)
    if author:
        conditions.append("author = ?")
        params.append(author)
    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)
    
    # count total
    c.execute(f"SELECT COUNT(*) FROM poems {where}", params)
    total_count = c.fetchone()[0]
    total_pages = (total_count + per_page - 1) // per_page
    
    # fetch page
    c.execute(f"SELECT id, title, author, dynasty, text FROM poems {where} ORDER BY title LIMIT ? OFFSET ?", params + [per_page, offset])
    rows = c.fetchall()
    conn.close()
    
    poems = []
    for r in rows:
        text = r[4]
        word_count = len(text.split())
        if word_count > 50:
            words = text.split()
            preview = " ".join(words[:50]) + "..."
        else:
            preview = text
        poems.append({
            "id": r[0],
            "title": r[1],
            "author": r[2],
            "dynasty": r[3],
            "text": text,
            "text_preview": preview
        })
    
    return render_template("_poems_list.html", poems=poems, dynasty=dynasty, author=author, current_page=page, total_pages=total_pages)


if __name__ == "__main__":
    app.run(debug=True)
