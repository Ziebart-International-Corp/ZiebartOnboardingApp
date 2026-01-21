"""
Initialize the database tables for New Hire Application
Run this script to create all necessary tables in the SQL Server database
"""
from app import app, db
from models import (User, NewHire, Document, ChecklistItem, NewHireChecklist,
                    TrainingVideo, QuizQuestion, QuizAnswer, UserTrainingProgress, UserQuizResponse, UserTask,
                    DocumentSignatureField, DocumentSignature, DocumentAssignment, UserNotification)

def init_database():
    """Create all database tables"""
    with app.app_context():
        print("Creating database tables...")
        try:
            # Create all tables
            db.create_all()
            print("Database tables created successfully!")
            print("\nCreated tables:")
            print("  - users (for storing user information)")
            print("  - new_hires (for tracking new employee onboarding)")
            print("  - documents (for storing new hire paperwork)")
            print("  - checklist_items (for new hire onboarding tasks)")
            print("  - new_hire_checklists (for tracking task completion)")
            print("  - training_videos (for harassment training videos)")
            print("  - quiz_questions (for training video quiz questions)")
            print("  - quiz_answers (for quiz answer options)")
            print("  - user_training_progress (for tracking user training progress)")
            print("  - user_quiz_responses (for storing user quiz responses)")
            print("  - user_tasks (for tasks assigned to users)")
            print("  - document_signature_fields (for signature field locations on documents)")
            print("  - document_signatures (for storing user signatures on documents)")
            print("  - document_assignments (for assigning documents to users for signing)")
            print("  - user_notifications (for tracking which notifications users have viewed)")
            db_info = app.config['SQLALCHEMY_DATABASE_URI'].split('@')[1] if '@' in app.config['SQLALCHEMY_DATABASE_URI'] else 'Connected'
            print(f"\nDatabase: {db_info}")
        except Exception as e:
            print(f"Error creating tables: {str(e)}")
            print("\nTroubleshooting:")
            print("1. Verify SQL Server is accessible")
            print("2. Check database connection string in config.py")
            print("3. Ensure database 'NewHireApp' exists on the server")
            print("4. Verify user 'Developer' has CREATE TABLE permissions")
            raise

if __name__ == '__main__':
    init_database()
