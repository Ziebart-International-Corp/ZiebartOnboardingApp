"""
Add missing columns to new_hires table (role_id, access_revoked_at).
Run once: python add_new_hire_columns.py
Safe to run multiple times (skips columns that already exist).
"""
from app import app, db
from sqlalchemy import text


def add_columns():
    with app.app_context():
        columns = [
            ("role_id", "INT NULL"),
            ("access_revoked_at", "DATE NULL"),
        ]
        for col_name, col_type in columns:
            try:
                r = db.session.execute(text("""
                    SELECT 1 FROM sys.columns
                    WHERE object_id = OBJECT_ID('new_hires') AND name = :name
                """), {"name": col_name}).fetchone()
                if r:
                    print(f"Column {col_name} already exists, skipping.")
                    continue
                db.session.execute(text(f"ALTER TABLE new_hires ADD [{col_name}] {col_type}"))
                db.session.commit()
                print(f"Added column: {col_name}")
            except Exception as e:
                db.session.rollback()
                print(f"Error adding {col_name}: {e}")
        # Optional: add FK for role_id if roles table exists (skip if already present or roles missing)
        try:
            r = db.session.execute(text("""
                SELECT 1 FROM sys.foreign_keys fk
                INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
                INNER JOIN sys.columns c ON c.object_id = fkc.parent_object_id AND c.column_id = fkc.parent_column_id
                WHERE OBJECT_NAME(fk.parent_object_id) = 'new_hires' AND c.name = 'role_id'
            """)).fetchone()
            if r:
                print("FK new_hires.role_id -> roles already exists, skipping.")
            else:
                db.session.execute(text("""
                    ALTER TABLE new_hires
                    ADD CONSTRAINT FK_new_hires_role_id FOREIGN KEY (role_id) REFERENCES roles(id)
                """))
                db.session.commit()
                print("Added FK: new_hires.role_id -> roles(id)")
        except Exception as e:
            db.session.rollback()
            print(f"FK optional (roles table may not exist or FK already there): {e}")
        print("Done.")


if __name__ == "__main__":
    add_columns()
