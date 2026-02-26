"""
Fix all il71-related names in the database: update usernames, emails, names, and roles.
Add a couple more il71 people. Roles: Ziebart - Detailing, Window Tinting, Rhino Lining.
Run from project root with venv: python fix_il71_names.py
"""
from datetime import datetime
from app import app
from models import (
    db,
    NewHire,
    User as UserModel,
    Store,
    UserTask,
    UserTrainingProgress,
    DocumentSignature,
    DocumentTypedFieldValue,
    DocumentAssignment,
    UserNotification,
)
from werkzeug.security import generate_password_hash

# Realistic names, usernames, emails and roles for Ziebart (detailing, window tinting, rhino lining)
IL71_REPLACEMENTS = [
    {"username": "mjohnson", "email": "mjohnson@il71.com", "first_name": "Marcus", "last_name": "Johnson", "department": "Detailing", "position": "Detail Specialist"},
    {"username": "dchen", "email": "dchen@il71.com", "first_name": "David", "last_name": "Chen", "department": "Window Tinting", "position": "Tint Technician"},
    {"username": "jrodriguez", "email": "jrodriguez@il71.com", "first_name": "James", "last_name": "Rodriguez", "department": "Rhino Lining", "position": "Bed Liner Technician"},
    {"username": "swilliams", "email": "swilliams@il71.com", "first_name": "Sarah", "last_name": "Williams", "department": "Detailing", "position": "Detail Specialist"},
    {"username": "mtorres", "email": "mtorres@il71.com", "first_name": "Michael", "last_name": "Torres", "department": "Window Tinting", "position": "Tint Technician"},
    {"username": "cmartinez", "email": "cmartinez@il71.com", "first_name": "Chris", "last_name": "Martinez", "department": "Rhino Lining", "position": "Bed Liner Technician"},
    {"username": "agarcia", "email": "agarcia@il71.com", "first_name": "Amanda", "last_name": "Garcia", "department": "Detailing", "position": "Detail Specialist"},
    {"username": "rthompson", "email": "rthompson@il71.com", "first_name": "Ryan", "last_name": "Thompson", "department": "Window Tinting", "position": "Tint Technician"},
]

DEFAULT_PASSWORD_NEW_HIRES = "Ziebart1!"  # For newly added il71 users; they can change on first login


def is_il71_record(nh):
    """True if this new hire looks like il71 test data."""
    first = (nh.first_name or "").lower()
    last = (nh.last_name or "").lower()
    email = (nh.email or "").lower()
    username = (nh.username or "").lower()
    if "il71" in first or "il71" in last or "il71" in email or "il71" in username:
        return True
    if "@il71.com" in email:
        return True
    if first in ("test", "testing", "sammy") and ("il71" in last or "person" in last):
        return True
    return False


def update_username_in_all_tables(old_username, new_username):
    """Update username in all tables that reference it (except new_hires and users; caller updates those)."""
    for model, attr in [
        (UserTask, "username"),
        (UserTrainingProgress, "username"),
        (DocumentSignature, "username"),
        (DocumentTypedFieldValue, "username"),
        (DocumentAssignment, "username"),
        (UserNotification, "username"),
    ]:
        try:
            updated = model.query.filter_by(**{attr: old_username}).update({attr: new_username})
            if updated:
                print(f"    Updated {model.__tablename__}: {updated} row(s)")
        except Exception as e:
            print(f"    Warning: {model.__tablename__}: {e}")


def main():
    with app.app_context():
        # ----- 1) Update existing il71 new hires: username, email, name, department, position -----
        all_nh = NewHire.query.filter(NewHire.status != "removed").all()
        il71_nh = [nh for nh in all_nh if is_il71_record(nh)]
        if il71_nh:
            print(f"Found {len(il71_nh)} il71-related new hire(s). Updating usernames, emails, names, and roles.\n")
            for i, nh in enumerate(il71_nh):
                repl = IL71_REPLACEMENTS[i % len(IL71_REPLACEMENTS)]
                old_username = nh.username
                new_username = repl["username"]
                new_email = repl["email"]
                if old_username == new_username and (nh.first_name, nh.last_name, nh.email) == (
                    repl["first_name"],
                    repl["last_name"],
                    new_email,
                ):
                    print(f"  Skip (already set): {old_username}")
                    continue
                # Update new_hires
                nh.username = new_username
                nh.first_name = repl["first_name"]
                nh.last_name = repl["last_name"]
                nh.email = new_email
                nh.department = repl["department"]
                nh.position = repl["position"]
                print(f"  NewHire: {old_username} -> {new_username} ({nh.first_name} {nh.last_name}) {new_email}")
                # Update all other tables that reference this username
                update_username_in_all_tables(old_username, new_username)
                # Update users table (login account)
                user = UserModel.query.filter_by(username=old_username).first()
                if user:
                    user.username = new_username
                    user.email = new_email
                    if hasattr(user, "full_name"):
                        user.full_name = f"{nh.first_name} {nh.last_name}"
                    print(f"    User: {old_username} -> {new_username}, email -> {new_email}")

            db.session.commit()
            print(f"\nCommitted updates for {len(il71_nh)} existing record(s).\n")
        else:
            print("No existing il71-related new hire records found.\n")

        # ----- 2) Add a couple more il71 people (new NewHire + User) -----
        new_hire_usernames = {nh.username for nh in NewHire.query.filter(NewHire.status != "removed").all()}
        to_add = [r for r in IL71_REPLACEMENTS if r["username"] not in new_hire_usernames][:2]
        if not to_add:
            print("No additional il71 people to add (all 8 already exist as new hires).")
            return

        store = Store.query.first()
        store_id = store.id if store else None
        created_by = "fix_il71_names.py"

        for repl in to_add:
            un = repl["username"]
            if NewHire.query.filter_by(username=un).first():
                print(f"  Skip add (already exists): {un}")
                continue
            email = repl["email"]
            first = repl["first_name"]
            last = repl["last_name"]
            dept = repl["department"]
            pos = repl["position"]
            # Create NewHire
            nh = NewHire(
                username=un,
                first_name=first,
                last_name=last,
                email=email,
                department=dept,
                position=pos,
                status="pending",
                created_by=created_by,
                store_id=store_id,
            )
            db.session.add(nh)
            db.session.flush()
            # Create or update User so they can log in
            user = UserModel.query.filter_by(username=un).first()
            if not user:
                user = UserModel(
                    username=un,
                    email=email,
                    role="user",
                    password_hash=generate_password_hash(DEFAULT_PASSWORD_NEW_HIRES),
                    store_id=store_id,
                )
                if hasattr(UserModel, "full_name"):
                    user.full_name = f"{first} {last}"
                db.session.add(user)
                print(f"  Added: {first} {last} ({un}, {email}) - {dept} / {pos}  [password: {DEFAULT_PASSWORD_NEW_HIRES}]")
            else:
                user.email = email
                if hasattr(user, "full_name"):
                    user.full_name = f"{first} {last}"
                if hasattr(user, "store_id"):
                    user.store_id = store_id
                print(f"  Added NewHire (User existed): {first} {last} ({un}) - {dept} / {pos}")

        if to_add:
            db.session.commit()
            print(f"\nCommitted {len(to_add)} new il71 record(s).")

        # ----- 3) Ensure every il71 User has a NewHire (fix mismatch so checklist list shows them) -----
        il71_users = UserModel.query.filter(UserModel.email.like("%@il71.com")).all()
        created = 0
        for user in il71_users:
            if user.role == "admin":
                continue
            existing = NewHire.query.filter_by(username=user.username).first()
            if existing and existing.status != "removed":
                continue
            if existing and existing.status == "removed":
                existing.status = "pending"
                existing.email = getattr(user, "email", None) or existing.email
                if hasattr(user, "full_name") and user.full_name:
                    parts = (user.full_name or "").strip().split(None, 1)
                    existing.first_name = parts[0] or existing.first_name
                    existing.last_name = (parts[1] if len(parts) > 1 else "") or existing.last_name
                print(f"  Restored NewHire for {user.username} (was removed).")
                created += 1
                continue
            # No NewHire: create one so they appear on checklist list
            full = (getattr(user, "full_name", None) or "").strip() or user.username
            parts = full.split(None, 1)
            first = parts[0] or user.username
            last = (parts[1] if len(parts) > 1 else "") or ""
            nh = NewHire(
                username=user.username,
                first_name=first,
                last_name=last,
                email=getattr(user, "email", None) or f"{user.username}@il71.com",
                status="pending",
                created_by="fix_il71_names.py(sync)",
                store_id=getattr(user, "store_id", None),
            )
            db.session.add(nh)
            print(f"  Created missing NewHire for {user.username} ({first} {last}) so checklist appears.")
            created += 1
        if created:
            db.session.commit()
            print(f"\nSynced {created} NewHire record(s) for il71 users.")


if __name__ == "__main__":
    main()
