"""One-off utility script: executes explain.sql against poems.db for query analysis."""
import sqlite3

with sqlite3.connect("poems.db") as conn:
    sql = open("explain.sql", "r", encoding="utf-8").read()
    conn.executescript(sql)