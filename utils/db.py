import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "school_v2.db")


def is_postgres():
    return os.environ.get("DATABASE_URL") is not None


def get_db():
    if is_postgres():
        return psycopg2.connect(
            os.environ.get("DATABASE_URL"),
            cursor_factory=RealDictCursor
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def convert_query(query: str) -> str:
    if is_postgres():
        return query.replace("?", "%s")
    return query


def fetch_one(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(convert_query(query), params)
    row = cursor.fetchone()
    conn.close()
    return row


def fetch_all(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(convert_query(query), params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def execute_commit(query, params=()):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(convert_query(query), params)
    conn.commit()
    conn.close()


def insert_and_get_id(query, params=()):
    conn = get_db()
    cursor = conn.cursor()

    try:
        if is_postgres():
            cursor.execute(convert_query(query + " RETURNING id"), params)
            row = cursor.fetchone()
            new_id = row["id"]
        else:
            cursor.execute(convert_query(query), params)
            new_id = cursor.lastrowid

        conn.commit()
        return new_id

    finally:
        conn.close()