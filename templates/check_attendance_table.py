from app import app, get_db

with app.app_context():
    conn = get_db()

    rows = conn.execute(
        "PRAGMA table_info(attendance)"
    ).fetchall()

    print("\nATTENDANCE TABLE COLUMNS")
    print("=" * 60)

    for row in rows:
        try:
            print(dict(row))
        except (TypeError, ValueError):
            print(row)

    print("=" * 60)