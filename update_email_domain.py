"""
Script to update email domain for existing records
Updates emails from @company.local to @ziebart.com (or configured domain)
"""
import sys
import os

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import NewHire, User as UserModel
import config

def update_email_domains():
    """Update email domains for existing records"""
    old_domain = 'company.local'
    new_domain = config.EMAIL_DOMAIN if hasattr(config, 'EMAIL_DOMAIN') else 'ziebart.com'
    
    with app.app_context():
        updated_new_hires = 0
        updated_users = 0
        
        # Update NewHire records
        new_hires = NewHire.query.all()
        for hire in new_hires:
            if hire.email and f'@{old_domain}' in hire.email:
                old_email = hire.email
                hire.email = hire.email.replace(f'@{old_domain}', f'@{new_domain}')
                updated_new_hires += 1
                print(f"Updated NewHire {hire.username}: {old_email} -> {hire.email}")
        
        # Update User records
        users = UserModel.query.all()
        for user in users:
            if user.email and f'@{old_domain}' in user.email:
                old_email = user.email
                user.email = user.email.replace(f'@{old_domain}', f'@{new_domain}')
                updated_users += 1
                print(f"Updated User {user.username}: {old_email} -> {user.email}")
        
        # Commit changes
        if updated_new_hires > 0 or updated_users > 0:
            db.session.commit()
            print(f"\n[SUCCESS] Updated {updated_new_hires} NewHire records and {updated_users} User records")
            print(f"  Changed email domain from @{old_domain} to @{new_domain}")
        else:
            print(f"\n[INFO] No records found with @{old_domain} email domain")
            print(f"  All emails are already using @{new_domain} or other domains")

if __name__ == '__main__':
    try:
        update_email_domains()
    except Exception as e:
        print(f"Error updating email domains: {str(e)}")
        sys.exit(1)
