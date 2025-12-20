# utils/database_utilities.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

@contextmanager
def db_connection():
    """Context manager for database connections."""
    conn = None
    try:
        conn = get_db_connection()
        yield conn
    finally:
        if conn:
            conn.close()

@contextmanager
def db_cursor(commit=False):
    """Context manager for database cursors with optional commit."""
    with db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                yield cur
                if commit:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise