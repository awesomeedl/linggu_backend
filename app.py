from flask import Flask, render_template, request
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
import datetime
import random
import urllib.parse

load_dotenv()

app = Flask(__name__)
engine = create_engine(os.environ["DATABASE_URL"])

def get_daily_poem() -> None | int:
    """Return a poem chosen pseudorandomly but deterministically for the current day."""
    with engine.connect() as conn:
        total = int(conn.execute(text("SELECT COUNT(*) FROM poems")).scalar() or 0)

    if total == 0:
        return None

    # seed with current date so it changes every day
    today = datetime.date.today().isoformat()
    rng = random.Random(today)
    index = rng.randrange(total)

    return index


@app.route("/")
def index():
    """Render the main page shell; HTMX will request the daily poem on load."""
    return render_template("index.html")


@app.route("/daily")
def daily_view():
    """Redirect to today's deterministically chosen daily poem."""
    return poem_by_id(get_daily_poem())


@app.route("/poem/<int:poem_id>")
def poem_by_id(poem_id):
    """Return a single poem fragment (HTMX) or the full page shell for direct navigation."""
    current_url = request.full_path

    if 'HX-Request' not in request.headers or 'HX-History-Restore-Request' in request.headers:
        # If this is a normal page load (not an htmx request) or a history restore, 
        # redirect to the poem detail page
        return render_template("index.html", initial_load_url=current_url)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, title, author, dynasty, text FROM poems WHERE id = :id"),
            {"id": poem_id}
        ).fetchone()

    poem = None
    if row:
        poem = {
            "id": row[0],
            "title": row[1],
            "author": row[2],
            "dynasty": row[3],
            "text": row[4],
        }
    return render_template("_poem.html", poem=poem)


@app.route("/search")
def search():
    """Full-text search over poems using SQLite FTS; returns a paginated poem list fragment."""
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
        with engine.connect() as conn:
            rows = conn.execute(
                text("""SELECT poems.id, poems.title, poems.author, poems.dynasty, poems.text,
                              SUBSTR(poems.text, 1, 200) as preview,
                              COUNT(*) OVER() as total
                       FROM poems
                       JOIN poem_fts ON poems.rowid = poem_fts.rowid
                       WHERE poem_fts MATCH :q
                       LIMIT :limit OFFSET :offset"""),
                {"q": q, "limit": per_page, "offset": offset}
            ).fetchall()

        if rows:
            total_count = rows[0][6]
            total_pages = (total_count + per_page - 1) // per_page

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
                           base_url=f"/search?search={urllib.parse.quote(q)}")


@app.route("/dynasties")
def dynasties():
    """List all dynasties with their author counts."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT dynasty, COUNT(*) FROM view_dynasty_author_counts GROUP BY dynasty ORDER BY dynasty")
        ).fetchall()

    dyn_list = [{"name": dyn, "author_count": count} for dyn, count in rows]
    
    return render_template("_dynasties.html", dynasties=dyn_list)

@app.route("/dynasties/<string:dynasty>/authors")
def dynasty_authors(dynasty):
    """Return a paginated list of authors for a given dynasty."""
    if "HX-Request" not in request.headers or "HX-History-Restore-Request" in request.headers:
        return render_template("index.html", initial_load_url=request.full_path)

    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT author, poem_count
                FROM view_dynasty_author_counts
                WHERE dynasty = :dynasty
                ORDER BY author
                LIMIT :limit OFFSET :offset
            """),
            {"dynasty": dynasty, "limit": per_page, "offset": offset}
        ).fetchall()

        total_authors = int(conn.execute(
            text("SELECT COUNT(*) FROM view_dynasty_author_counts WHERE dynasty = :dynasty"),
            {"dynasty": dynasty}
        ).scalar() or 0)

    authors = [{'name': r[0], 'count': r[1]} for r in rows]
    has_next = (offset + per_page) < total_authors
    
    return render_template("_authors_list.html", 
                           dynasty=dynasty, 
                           authors=authors, 
                           current_page=page,
                           has_next=has_next)

@app.route("/poems")
def poems_list():
    """Return a paginated list of poems, optionally filtered by dynasty and/or author."""
    if "HX-Request" not in request.headers or "HX-History-Restore-Request" in request.headers:
        return render_template("index.html", initial_load_url=request.full_path)

    dynasty = request.args.get("dynasty", "").strip()
    author = request.args.get("author", "").strip()
    page = request.args.get("page", 1, type=int)
    if page < 1: page = 1
    
    per_page = 10
    offset = (page - 1) * per_page
    
    conditions = []
    params = {}
    if dynasty:
        conditions.append("dynasty = :dynasty")
        params["dynasty"] = dynasty
    if author:
        conditions.append("author = :author")
        params["author"] = author

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["limit"] = per_page
    params["offset"] = offset

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, title, author, dynasty, text,
                       SUBSTR(text, 1, 200) as preview,
                       COUNT(*) OVER() as total
                FROM poems {where}
                ORDER BY title
                LIMIT :limit OFFSET :offset
            """),
            params
        ).fetchall()

    total_count = rows[0][6] if rows else 0
    total_pages = (total_count + per_page - 1) // per_page

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
                           base_url=f"/poems?dynasty={urllib.parse.quote(dynasty)}&author={urllib.parse.quote(author)}")

if __name__ == "__main__":
    app.run(debug=True)
