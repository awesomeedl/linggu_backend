# Linggu Backend

This repository stores collections of Chinese poems and tools for importing them into an SQLite database.

## Flask/HTMX daily poem app

A simple web application serves a randomly selected poem every day from `poems.db` using Flask and HTMX.

### Setup

1. Create and activate your Python virtual environment (e.g. `python -m venv .venv` and `\.venv\Scripts\activate`).
2. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Ensure `poems.db` has been populated (use `import_poem.py`).

### Running

Start the development server:
```sh
python app.py
```

Then open `http://127.0.0.1:5000/` in your browser. The landing page will load the poem for the current day and includes a **search bar** at the top. You can type keywords and press Enter to look up other poems; results appear below and clicking one will replace the displayed poem.

For convenience there is also an API endpoint at `/api/poem` which returns the same poem in JSON form.

### Browsing poems by dynasty/author

Use the sidebar on the left to explore poems by dynasty. The list is collapsible and scrollable when there are many entries. Clicking a dynasty shows all poems from that era; clicking an author filters further. When an author is chosen their name is shown next to the dynasty both in the sidebar and in the main poem list header, giving context as you browse.
