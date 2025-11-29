import os
import sqlite3
import json
from xml.dom import INDEX_SIZE_ERR

import poem_importer

DB_PATH = "poems.db"
INDEX = "index.json"
DATA_ROOT = "source/"

SCHEMA = """
CREATE TABLE IF NOT EXISTS poems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    author TEXT,
    dynasty TEXT,
    text TEXT
);


CREATE VIRTUAL TABLE IF NOT EXISTS poem_fts USING fts5(
    title,
    author,
    dynasty,
    text,
    content='poems',
    content_rowid='id'
);


CREATE TRIGGER IF NOT EXISTS poems_ai AFTER INSERT ON poems BEGIN
    INSERT INTO poem_fts(rowid, title, author, dynasty, text)
    VALUES (new.id, new.title, new.author, new.dynasty, new.text);
END;


CREATE TRIGGER IF NOT EXISTS poems_ad AFTER DELETE ON poems BEGIN
    INSERT INTO poem_fts(poem_fts, rowid, title, author, dynasty, text)
    VALUES('delete', old.id, old.title, old.author, old.dynasty, old.text);
END;


CREATE TRIGGER IF NOT EXISTS poems_au AFTER UPDATE ON poems BEGIN
    INSERT INTO poem_fts(poem_fts, rowid, title, author, dynasty, text)
    VALUES('delete', old.id, old.title, old.author, old.dynasty, old.text);
    INSERT INTO poem_fts(rowid, title, author, dynasty, text)
    VALUES (new.id, new.title, new.author, new.dynasty, new.text);
END;
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript(SCHEMA)
    conn.commit()
    conn.close()

def import_all():
    

    datasets: dict = json.load(open(INDEX, "r", encoding="utf-8"))["datasets"]

    for d in datasets.values():
        path = d["path"]
        tag = d["tag"]
        dynasty = d["dynasty"]
        data_root = os.path.join(DATA_ROOT, path)
        importer = poem_importer.PoemImporter(DB_PATH, data_root, dynasty, tag)
        
        importer.import_all()


if __name__ == "__main__":
    init_db()
    import_all()
