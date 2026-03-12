from flask import Flask, render_template, request
import sqlite3
import datetime
import random
import urllib.parse # Make sure this is imported at the top

app = Flask(__name__)
DB_PATH = "poems.db"

def get_daily_poem():
    """Return a poem chosen pseudorandomly but deterministically for the current day."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM poems")
        total = c.fetchone()[0]

    if total == 0:
        return None

    # seed with current date so it changes every day
    today = datetime.date.today().isoformat()
    rng = random.Random(today)
    index = rng.randrange(total)

    return index


# Front page
@app.route("/")
def index():
    # initial page loads htmx container that will request the daily poem
    return render_template("index.html")

# Daily poem recommendation
@app.route("/daily")
def daily_view():
    return poem_by_id(get_daily_poem())

# Get poem by ID
@app.route("/poem/<int:poem_id>")
def poem_by_id(poem_id):
    current_url = request.full_path

    if 'HX-Request' not in request.headers or 'HX-History-Restore-Request' in request.headers:
        # If this is a normal page load (not an htmx request) or a history restore, 
        # redirect to the poem detail page
        return render_template("index.html", initial_load_url=current_url)

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


@app.route("/search")
def search():
    if "HX-Request" not in request.headers or "HX-History-Restore-Request" in request.headers:
        return render_template("index.html", initial_load_url=request.full_path)

    q = request.args.get("search", "").strip()
    page = request.args.get("page", 1, type=int)
    if page < 1: page = 1
    
    per_page = 10
    offset = (page - 1) * per_page

    rows = []
    total_pages = 0

    if q:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            # Added pagination Window Function and LIMIT just like poems_list()
            c.execute(
                """SELECT poems.id, poems.title, poems.author, poems.dynasty, poems.text,
                          SUBSTR(poems.text, 1, 200) as preview,
                          COUNT(*) OVER() as total
                   FROM poems 
                   JOIN poem_fts ON poems.rowid = poem_fts.rowid 
                   WHERE poem_fts MATCH ? 
                   LIMIT ? OFFSET ?""",
                (q, per_page, offset)
            )
            rows = c.fetchall()

        if rows:
            total_count = rows[0][6]
            total_pages = (total_count + per_page - 1) // per_page

    # Modify this if using the helper function you added previously
    poems = [{
        "id": r[0], "title": r[1], "author": r[2], "dynasty": r[3],
        "text_preview": r[5] + "...",
        "detail_url": f"/poem/{r[0]}?dynasty=search&q={urllib.parse.quote(q)}"
    } for r in rows]

    return render_template("_poems_list.html", 
                           poems=poems, 
                           list_title=f'Search results for "{q}"' if q else "Search results",
                           empty_message="No matches found.",
                           current_page=page,
                           total_pages=total_pages,
                           # --- Generic Pagination Vars ---
                           base_url=f"/search?search={urllib.parse.quote(q)}")


@app.route("/dynasties")
def dynasties():
    # Load only dynasties, skipping authors for performance
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT dynasty, COUNT(*) FROM view_dynasty_author_counts GROUP BY dynasty ORDER BY dynasty")
    rows = c.fetchall()
    conn.close()

    dyn_list = [{"name": dyn, "author_count": count} for dyn, count in rows]
    
    return render_template("_dynasties.html", dynasties=dyn_list)

@app.route("/dynasties/<string:dynasty>/authors")
def dynasty_authors(dynasty):
    if "HX-Request" not in request.headers or "HX-History-Restore-Request" in request.headers:
        return render_template("index.html", initial_load_url=request.full_path)

    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT author, poem_count
            FROM view_dynasty_author_counts
            WHERE dynasty = ?
            ORDER BY author
            LIMIT ? OFFSET ?
        """, (dynasty, per_page, offset))
        rows = c.fetchall()
        
        c.execute("SELECT COUNT(*) FROM view_dynasty_author_counts WHERE dynasty = ?", (dynasty,))
        total_authors = c.fetchone()[0]

    authors = [{'name': r[0], 'count': r[1]} for r in rows]
    has_next = (offset + per_page) < total_authors
    
    return render_template("_authors_list.html", 
                           dynasty=dynasty, 
                           authors=authors, 
                           current_page=page,
                           has_next=has_next)

@app.route("/poems")
def poems_list():
    if "HX-Request" not in request.headers or "HX-History-Restore-Request" in request.headers:
        return render_template("index.html", initial_load_url=request.full_path)

    # Use .get() default values to avoid extra try/except blocks
    dynasty = request.args.get("dynasty", "").strip()
    author = request.args.get("author", "").strip()
    page = request.args.get("page", 1, type=int)
    if page < 1: page = 1
    
    per_page = 10
    offset = (page - 1) * per_page
    
    # Context manager handles closing the connection automatically
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        
        conditions = []
        params = []
        if dynasty:
            conditions.append("dynasty = ?")
            params.append(dynasty)
        if author:
            conditions.append("author = ?")
            params.append(author)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Optimized query: Fetching preview via SQL and total count via Window Function
        query = f"""
            SELECT id, title, author, dynasty, text, 
                   SUBSTR(text, 1, 200) as preview,
                   COUNT(*) OVER() as total
            FROM poems {where} 
            ORDER BY title 
            LIMIT ? OFFSET ?
        """
        c.execute(query, params + [per_page, offset])
        rows = c.fetchall()

    total_count = rows[0][6] if rows else 0
    total_pages = (total_count + per_page - 1) // per_page

    # Cleaner list comprehension
    poems = [{
        "id": r[0], "title": r[1], "author": r[2], "dynasty": r[3],
        "text": r[4], "text_preview": r[5] + "..."
    } for r in rows]
    

    return render_template("_poems_list.html", 
                           poems=poems, 
                           list_title=f"{dynasty}/{author}",
                           empty_message="No poems found.",
                           current_page=page, 
                           total_pages=total_pages,
                           # --- Generic Pagination Vars ---
                           base_url=f"/poems?dynasty={urllib.parse.quote(dynasty)}&author={urllib.parse.quote(author)}")

if __name__ == "__main__":
    app.run(debug=True)
