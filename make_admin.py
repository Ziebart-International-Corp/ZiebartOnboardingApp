"""
Script to assign admin role to a user
Usage: python make_admin.py <username>
"""
from app import app, db
from models import User as UserModel

def make_admin(username):
    """Assign admin role to a user"""
    with app.app_context():
        # Find user by username
        user = UserModel.query.filter_by(username=username).first()
        
        if not user:
            # Create new user if doesn't exist
            user = UserModel(
                username=username,
                role='admin'
            )
            db.session.add(user)
            print(f'User {username} created and assigned admin role.')
        else:
            user.role = 'admin'
            print(f'Admin role assigned to {username}.')
        
        db.session.commit()
        print(f'Success! {username} is now an admin.')

if __name__ == '__main__':
    import sys
    username = sys.argv[1] if len(sys.argv) > 1 else 'aka'
    make_admin(username)
