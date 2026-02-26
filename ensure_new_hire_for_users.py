"""
Create missing NewHire records for Users that don't have one.
Fixes the case where a user can log in but doesn't appear on the "Select User to View/Update Checklist" list.
Run from project root with venv: python ensure_new_hire_for_users.py
"""
from app import app
from models import db, NewHire, User as UserModel


def main():
    with app.app_context():
        # Find users (role=user, not admin) that have no NewHire or only a removed one
        users = UserModel.query.filter(UserModel.role == "user").all()
        created = 0
        restored = 0
        for user in users:
            if user.role == "admin":
                continue
            nh = NewHire.query.filter_by(username=user.username).first()
            if nh:
                if nh.status != "removed":
                    continue
                # Restore removed NewHire so they show on checklist list again
                nh.status = "pending"
                nh.email = getattr(user, "email", None) or nh.email
                if hasattr(user, "full_name") and user.full_name:
                    parts = (user.full_name or "").strip().split(None, 1)
                    nh.first_name = parts[0] or nh.first_name
                    nh.last_name = (parts[1] if len(parts) > 1 else "") or nh.last_name
                print(f"  Restored NewHire: {user.username}")
                restored += 1
                continue
            # No NewHire: create one
            full = (getattr(user, "full_name", None) or "").strip() or user.username
            parts = full.split(None, 1)
            first = parts[0] or user.username
            last = (parts[1] if len(parts) > 1 else "") or ""
            email = getattr(user, "email", None) or f"{user.username}@example.com"
            nh = NewHire(
                username=user.username,
                first_name=first,
                last_name=last,
                email=email,
                status="pending",
                created_by="ensure_new_hire_for_users.py",
                store_id=getattr(user, "store_id", None),
            )
            db.session.add(nh)
            print(f"  Created NewHire: {user.username} ({first} {last})")
            created += 1

        if created or restored:
            db.session.commit()
            print(f"\nDone. Created {created}, restored {restored} NewHire record(s).")
        else:
            print("No users missing a NewHire record.")


if __name__ == "__main__":
    main()
