"""
Add missing columns to new_hires table (role_id, access_revoked_at).
Run once: python add_new_hire_columns.py
Safe to run multiple times (skips columns that already exist).
PostgreSQL/CockroachDB version.
"""
from app import app, db
from sqlalchemy import text


def add_columns():
    with app.app_context():
        columns = [
            ("role_id", "INTEGER NULL"),
            ("access_revoked_at", "DATE NULL"),
        ]
        for col_name, col_type in columns:
            try:
                r = db.session.execute(text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'new_hires' AND column_name = :name
                """), {"name": col_name}).fetchone()
                if r:
                    print(f"Column {col_name} already exists, skipping.")
                    continue
                db.session.execute(text(f"ALTER TABLE new_hires ADD COLUMN {col_name} {col_type}"))
                db.session.commit()
                print(f"Added column: {col_name}")
            except Exception as e:
                db.session.rollback()
                print(f"Error adding {col_name}: {e}")
        # Optional: add FK for role_id if roles table exists (skip if already present or roles missing)
        try:
            r = db.session.execute(text("""
                SELECT 1 FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = 'new_hires' AND tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.column_name = 'role_id'
            """)).fetchone()
            if r:
                print("FK new_hires.role_id -> roles already exists, skipping.")
            else:
                db.session.execute(text("""
                    ALTER TABLE new_hires
                    ADD CONSTRAINT fk_new_hires_role_id FOREIGN KEY (role_id) REFERENCES roles(id)
                """))
                db.session.commit()
                print("Added FK: new_hires.role_id -> roles(id)")
        except Exception as e:
            db.session.rollback()
            print(f"FK optional (roles table may not exist or FK already there): {e}")
        print("Done.")


if __name__ == "__main__":
    add_columns()
