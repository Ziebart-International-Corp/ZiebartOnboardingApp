"""
One-off script: delete the "Phishing Training" video from the database.
Run from project root with your venv activated.

  python delete_phishing_training_video.py

Important: To remove the video from the LIVE site (Vercel), set DATABASE_URL
in your .env to your Neon connection string (same DB Vercel uses) before
running. If .env points at SQL Server, the delete will only affect that DB.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import app
from models import (
    db,
    TrainingVideo,
    QuizQuestion,
    QuizAnswer,
    UserTrainingProgress,
    UserQuizResponse,
    UserTask,
    UserNotification,
    new_hire_required_training,
)

TITLE = "Phishing Training"


def main():
    with app.app_context():
        video = TrainingVideo.query.filter_by(title=TITLE).first()
        if not video:
            print(f'No video found with title "{TITLE}". Nothing to do.')
            return 0
        vid = video.id
        print(f'Found: id={vid} title={video.title!r}. Deleting...')
        try:
            # Same order as in app delete_training_video (plus user_quiz_responses first)
            db.session.execute(
                new_hire_required_training.delete().where(
                    new_hire_required_training.c.video_id == vid
                )
            )
            question_ids = [q.id for q in video.questions]
            if question_ids:
                UserQuizResponse.query.filter(
                    UserQuizResponse.question_id.in_(question_ids)
                ).delete(synchronize_session=False)
            for question in video.questions:
                QuizAnswer.query.filter_by(question_id=question.id).delete()
            QuizQuestion.query.filter_by(video_id=vid).delete()
            UserTrainingProgress.query.filter_by(video_id=vid).delete()
            UserTask.query.filter(
                UserTask.task_type == 'training',
                UserTask.notes == f'video_id:{vid}'
            ).delete(synchronize_session=False)
            UserNotification.query.filter_by(
                notification_type='training',
                notification_id=str(vid)
            ).delete(synchronize_session=False)
            db.session.delete(video)
            db.session.commit()
            print(f'Deleted "{TITLE}" (id={vid}) and all related rows.')
        except Exception as e:
            db.session.rollback()
            print(f'Error: {e}')
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
