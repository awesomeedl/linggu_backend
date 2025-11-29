import os
import sqlite3
import json
import threading
import queue
import concurrent.futures
import traceback


EXCLUDES = {"README.md", "表面结构字.json", "authors.song.json", "authors.tang.json"}


class PoemImporter:
    """Import poems from JSON files into SQLite with multithreading."""

    def __init__(self, db_path, data_root, dynasty, tag):
        """
        Args:
            db_path: Path to SQLite database file
            data_root: Root directory containing JSON poem files
            dynasty: Dynasty name to associate with imported poems
        """
        self.db_path = db_path
        self.data_root = data_root
        self.dynasty = dynasty
        self.tag = tag

    def insert_poem_with_conn(self, conn, poem):
        """Insert a poem into both poems and poem_fts tables."""
        c = conn.cursor()
        c.execute(
            "INSERT INTO poems (title, author, dynasty, text) VALUES (?, ?, ?, ?)",
            (poem.get("title", ""), poem.get("author", ""), self.dynasty, poem.get("text", ""))
        )

    def load_poems_from_file(self, path):
        """Load poems from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        poems = []
        for entry in data:
            text = "\n".join(entry.get(self.tag, []))
            poems.append({
                "title": entry.get("title", ""),
                "author": entry.get("author", ""),
                "text": text
            })
        return poems

    def import_all(self, max_workers=None, queue_maxsize=2000, commit_batch=200):
        """
        Parallel file parsing with a single DB writer.
        
        Args:
            max_workers: Number of parser threads (defaults to os.cpu_count() or 4)
            queue_maxsize: Backpressure for producers
            commit_batch: How many inserts before committing in writer
        """
        if max_workers is None:
            max_workers = max(1, (os.cpu_count() or 4))

        poems_queue = queue.Queue(maxsize=queue_maxsize)
        stop_event = threading.Event()

        def db_writer():
            conn = sqlite3.connect(self.db_path, timeout=30)
            inserted = 0
            try:
                while not (stop_event.is_set() and poems_queue.empty()):
                    try:
                        poem = poems_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    try:
                        self.insert_poem_with_conn(conn, poem)
                        inserted += 1
                        poems_queue.task_done()
                        if inserted % commit_batch == 0:
                            conn.commit()
                    except Exception:
                        print("DB writer error while inserting poem:")
                        traceback.print_exc()
                        poems_queue.task_done()
                # final commit
                conn.commit()
            finally:
                conn.close()

        def process_file(path):
            try:
                poems = self.load_poems_from_file(path)
                for p in poems:
                    poems_queue.put(p)  # blocks if queue full (backpressure)
                print(f"Loaded {len(poems)} poems from {path}")
            except Exception as e:
                print(f"Failed to load {path}: {e}")
                traceback.print_exc()

        # Start writer thread
        writer_thread = threading.Thread(target=db_writer, name="db-writer", daemon=True)
        writer_thread.start()

        # Walk files and submit parse tasks
        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for root, _, files in os.walk(self.data_root):
                for filename in files:
                    if filename in EXCLUDES:
                        print(f"Skipping excluded file {filename}")
                        continue
                    if filename.endswith(".json"):
                        path = os.path.join(root, filename)
                        print(f"Scheduling parse {path}")
                        futures.append(executor.submit(process_file, path))

            # wait for all parser tasks to finish
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception:
                    print("Parser thread raised an exception:")
                    traceback.print_exc()

        # Wait until queue is fully processed by writer
        poems_queue.join()
        # signal writer to stop and wait
        stop_event.set()
        writer_thread.join()
        print("Import complete.")
