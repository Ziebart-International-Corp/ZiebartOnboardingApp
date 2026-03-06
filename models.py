"""
Database models for the New Hire Application
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    """User model for storing user information. Login is by email + password."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    domain = db.Column(db.String(100))
    full_name = db.Column(db.String(200))
    email = db.Column(db.String(200), nullable=True, index=True)  # Used for login; unique per user
    password_hash = db.Column(db.String(255), nullable=True)  # Werkzeug hashed password
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    access_revoked_at = db.Column(db.Date, nullable=True)  # When set (and today >= this date), user cannot log in
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


# Association table for new hire required training videos
new_hire_required_training = db.Table('new_hire_required_training',
    db.Column('new_hire_id', db.Integer, db.ForeignKey('new_hires.id'), primary_key=True),
    db.Column('video_id', db.Integer, db.ForeignKey('training_videos.id'), primary_key=True)
)


class NewHire(db.Model):
    """New Hire model for tracking new employees"""
    __tablename__ = 'new_hires'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, index=True)  # Domain username
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(100))
    position = db.Column(db.String(100))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)  # Job role (for default docs)
    start_date = db.Column(db.Date)
    access_revoked_at = db.Column(db.Date, nullable=True)  # After this date user cannot log in
    status = db.Column(db.String(50), default='pending')  # pending, active, completed
    created_by = db.Column(db.String(100))  # Username of creator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.Column(db.Text)
    # Finale message shown to new hire when onboarding is complete (sent from admin checklist)
    finale_message = db.Column(db.Text, nullable=True)
    finale_message_sent_at = db.Column(db.DateTime, nullable=True)
    finale_document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)
    finale_message_dismissed_at = db.Column(db.DateTime, nullable=True)

    # Relationship to required training videos
    required_training_videos = db.relationship('TrainingVideo', 
                                                secondary=new_hire_required_training,
                                                backref='assigned_new_hires',
                                                lazy='dynamic')
    
    def __repr__(self):
        return f'<NewHire {self.first_name} {self.last_name}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'department': self.department,
            'position': self.position,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'access_revoked_at': self.access_revoked_at.isoformat() if self.access_revoked_at else None,
            'status': self.status,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'notes': self.notes
        }


class Document(db.Model):
    """Document model for storing new hire paperwork"""
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=True)  # Name shown to users; if null, original_filename is used
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)  # Size in bytes
    file_type = db.Column(db.String(100))  # MIME type
    description = db.Column(db.Text)
    is_visible = db.Column(db.Boolean, default=False)  # Visibility toggle for regular users
    uploaded_by = db.Column(db.String(100))  # Username of uploader
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Document {self.original_filename}>'
    
    @property
    def name_for_users(self):
        """Name to show to users (display_name if set, else original_filename)."""
        return (self.display_name or self.original_filename or '').strip() or self.original_filename

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'display_name': self.display_name,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'description': self.description,
            'is_visible': self.is_visible,
            'uploaded_by': self.uploaded_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# Job roles: default documents per role for onboarding
role_documents = db.Table('role_documents',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('document_id', db.Integer, db.ForeignKey('documents.id'), primary_key=True)
)


class Role(db.Model):
    """Job role - used in onboarding to pre-select default documents"""
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    description = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    default_documents = db.relationship(
        'Document',
        secondary=role_documents,
        backref=db.backref('roles', lazy='dynamic'),
        lazy='dynamic'
    )
    
    def __repr__(self):
        return f'<Role {self.name}>'


class ChecklistItem(db.Model):
    """Checklist item model for new hire onboarding tasks"""
    __tablename__ = 'checklist_items'
    
    id = db.Column(db.Integer, primary_key=True)
    task_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.String(100))  # Username or role (e.g., 'HR', 'IT', 'Manager')
    order = db.Column(db.Integer, default=0)  # Order in which tasks should be completed
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(100))  # Username of creator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ChecklistItem {self.task_name} (Order: {self.order})>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'task_name': self.task_name,
            'description': self.description,
            'assigned_to': self.assigned_to,
            'order': self.order,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class NewHireChecklist(db.Model):
    """Track checklist completion for specific new hires"""
    __tablename__ = 'new_hire_checklists'
    
    id = db.Column(db.Integer, primary_key=True)
    new_hire_id = db.Column(db.Integer, db.ForeignKey('new_hires.id'), nullable=False)
    checklist_item_id = db.Column(db.Integer, db.ForeignKey('checklist_items.id'), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    completed_by = db.Column(db.String(100))  # Username who completed it
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    new_hire = db.relationship('NewHire', backref='checklist_items')
    checklist_item = db.relationship('ChecklistItem', backref='new_hire_assignments')
    
    def __repr__(self):
        return f'<NewHireChecklist {self.new_hire_id} - {self.checklist_item_id}>'


class TrainingVideo(db.Model):
    """Training video model for harassment training"""
    __tablename__ = 'training_videos'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)  # Size in bytes
    duration = db.Column(db.Float)  # Duration in seconds
    video_type = db.Column(db.String(50), default='harassment')  # Type of training
    is_active = db.Column(db.Boolean, default=True)
    passing_score = db.Column(db.Integer, default=80)  # Minimum score to pass (percentage)
    max_attempts = db.Column(db.Integer, default=3)  # Max attempts before requiring retake
    uploaded_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<TrainingVideo {self.title}>'


class QuizQuestion(db.Model):
    """Quiz questions for training videos"""
    __tablename__ = 'quiz_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('training_videos.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), default='mid')  # 'mid' or 'end'
    video_timestamp = db.Column(db.Float)  # Time in seconds when question appears (for mid-video)
    order = db.Column(db.Integer, default=0)  # Order for end questions
    points = db.Column(db.Integer, default=1)  # Points for correct answer
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    video = db.relationship('TrainingVideo', backref='questions')
    
    def __repr__(self):
        return f'<QuizQuestion {self.id} for Video {self.video_id}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'video_id': self.video_id,
            'question_text': self.question_text,
            'question_type': self.question_type,
            'video_timestamp': self.video_timestamp,
            'order': self.order,
            'points': self.points,
            'answers': [{'id': a.id, 'answer_text': a.answer_text, 'is_correct': a.is_correct} for a in self.answers]
        }


class QuizAnswer(db.Model):
    """Answer options for quiz questions"""
    __tablename__ = 'quiz_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_questions.id'), nullable=False)
    answer_text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)
    
    # Relationship
    question = db.relationship('QuizQuestion', backref='answers')
    
    def __repr__(self):
        return f'<QuizAnswer {self.id} for Question {self.question_id}>'


class UserTrainingProgress(db.Model):
    """Track user progress through training videos"""
    __tablename__ = 'user_training_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, index=True)
    video_id = db.Column(db.Integer, db.ForeignKey('training_videos.id'), nullable=False)
    attempt_number = db.Column(db.Integer, default=1)
    score = db.Column(db.Float)  # Percentage score
    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    time_watched = db.Column(db.Float, default=0)  # Total seconds watched
    is_passed = db.Column(db.Boolean, default=False)
    is_completed = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    video = db.relationship('TrainingVideo', backref='user_progress')
    
    def __repr__(self):
        return f'<UserTrainingProgress {self.username} - Video {self.video_id} - Attempt {self.attempt_number}>'


class UserQuizResponse(db.Model):
    """Store individual user responses to quiz questions"""
    __tablename__ = 'user_quiz_responses'
    
    id = db.Column(db.Integer, primary_key=True)
    progress_id = db.Column(db.Integer, db.ForeignKey('user_training_progress.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_questions.id'), nullable=False)
    answer_id = db.Column(db.Integer, db.ForeignKey('quiz_answers.id'), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    responded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    progress = db.relationship('UserTrainingProgress', backref='responses')
    question = db.relationship('QuizQuestion')
    answer = db.relationship('QuizAnswer')
    
    def __repr__(self):
        return f'<UserQuizResponse {self.id} for Question {self.question_id}>'


class UserTask(db.Model):
    """User task model for tasks assigned to individual users"""
    __tablename__ = 'user_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, index=True)  # Username of assigned user
    task_title = db.Column(db.String(200), nullable=False)
    task_description = db.Column(db.Text)
    task_type = db.Column(db.String(50), default='general')  # 'general', 'training', 'document', 'form', etc.
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=True)  # Link to document if task_type is 'document'
    priority = db.Column(db.String(20), default='normal')  # 'low', 'normal', 'high', 'urgent'
    status = db.Column(db.String(20), default='pending')  # 'pending', 'in_progress', 'completed', 'cancelled'
    due_date = db.Column(db.Date)  # Optional due date
    assigned_by = db.Column(db.String(100))  # Username of admin who assigned the task
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)  # User notes or admin notes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<UserTask {self.task_title} for {self.username} ({self.status})>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'username': self.username,
            'task_title': self.task_title,
            'task_description': self.task_description,
            'task_type': self.task_type,
            'priority': self.priority,
            'status': self.status,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'assigned_by': self.assigned_by,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class DocumentSignatureField(db.Model):
    """Signature field locations on documents - where admins mark where users should sign"""
    __tablename__ = 'document_signature_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=False, default=1)  # Page number (1-indexed)
    x_position = db.Column(db.Float, nullable=False)  # X coordinate in browser pixels (relative to viewer)
    y_position = db.Column(db.Float, nullable=False)  # Y coordinate in browser pixels (relative to viewer)
    width = db.Column(db.Float, nullable=False, default=200)  # Width in browser pixels
    height = db.Column(db.Float, nullable=False, default=80)  # Height in browser pixels
    field_label = db.Column(db.String(200))  # Optional label (e.g., "Employee Signature")
    is_required = db.Column(db.Boolean, default=True)  # Whether signature is required
    signature_type = db.Column(db.String(20), default='image')  # 'image' or 'cryptographic'
    created_by = db.Column(db.String(100))  # Username of admin who created the field
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    document = db.relationship('Document', backref='signature_fields')
    
    def __repr__(self):
        return f'<DocumentSignatureField {self.id} on Document {self.document_id}, Page {self.page_number}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'page_number': self.page_number,
            'x_position': self.x_position,
            'y_position': self.y_position,
            'width': self.width,
            'height': self.height,
            'field_label': self.field_label,
            'is_required': self.is_required
        }


class DocumentSignature(db.Model):
    """User signatures on documents"""
    __tablename__ = 'document_signatures'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    signature_field_id = db.Column(db.Integer, db.ForeignKey('document_signature_fields.id'), nullable=True)  # Made nullable to preserve signatures when field is deleted
    username = db.Column(db.String(100), nullable=False, index=True)  # Username who signed
    signature_image = db.Column(db.Text, nullable=True)  # Base64 encoded signature image (for image-based)
    signature_hash = db.Column(db.String(64), nullable=True)  # SHA-256 hash of signed PDF (for cryptographic)
    certificate_serial = db.Column(db.String(200), nullable=True)  # Certificate serial number (for cryptographic)
    signature_type = db.Column(db.String(20), default='image')  # 'image' or 'cryptographic'
    signed_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))  # IP address when signed (for audit)
    user_agent = db.Column(db.String(500), nullable=True)  # Browser user agent
    consent_given = db.Column(db.Boolean, default=False)  # User consent for electronic signing
    
    # Stored field metadata (snapshot at time of signing) - preserves signature location even if field is deleted
    field_page_number = db.Column(db.Integer, nullable=True)  # Page number where signature was placed
    field_x_position = db.Column(db.Float, nullable=True)  # X coordinate where signature was placed
    field_y_position = db.Column(db.Float, nullable=True)  # Y coordinate where signature was placed
    field_width = db.Column(db.Float, nullable=True)  # Width of signature field
    field_height = db.Column(db.Float, nullable=True)  # Height of signature field
    field_label = db.Column(db.String(200), nullable=True)  # Label of the signature field
    
    # Relationships
    document = db.relationship('Document', backref='signatures')
    signature_field = db.relationship('DocumentSignatureField', backref='signatures')
    
    def __repr__(self):
        return f'<DocumentSignature {self.id} by {self.username} on Document {self.document_id}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'signature_field_id': self.signature_field_id,
            'username': self.username,
            'signed_at': self.signed_at.isoformat() if self.signed_at else None,
            'ip_address': self.ip_address
        }


class DocumentTypedField(db.Model):
    """Typed field locations on documents - where admins mark where users should type (name, date, etc.)"""
    __tablename__ = 'document_typed_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=False, default=1)  # Page number (1-indexed)
    x_position = db.Column(db.Float, nullable=False)  # X coordinate in browser pixels
    y_position = db.Column(db.Float, nullable=False)  # Y coordinate in browser pixels
    width = db.Column(db.Float, nullable=False, default=200)  # Width in browser pixels
    height = db.Column(db.Float, nullable=False, default=30)  # Height in browser pixels
    field_label = db.Column(db.String(200))  # Label (e.g., "Name", "Date")
    field_type = db.Column(db.String(20), default='text')  # 'text', 'date', 'name', etc.
    is_required = db.Column(db.Boolean, default=True)  # Whether field is required
    placeholder = db.Column(db.String(200))  # Placeholder text
    created_by = db.Column(db.String(100))  # Username of admin who created the field
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    document = db.relationship('Document', backref='typed_fields')
    
    def __repr__(self):
        return f'<DocumentTypedField {self.id} on Document {self.document_id}, Page {self.page_number}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'page_number': self.page_number,
            'x_position': self.x_position,
            'y_position': self.y_position,
            'width': self.width,
            'height': self.height,
            'field_label': self.field_label,
            'field_type': self.field_type,
            'is_required': self.is_required,
            'placeholder': self.placeholder
        }


class DocumentTypedFieldValue(db.Model):
    """User-entered values for typed fields"""
    __tablename__ = 'document_typed_field_values'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    typed_field_id = db.Column(db.Integer, db.ForeignKey('document_typed_fields.id'), nullable=False)
    username = db.Column(db.String(100), nullable=False, index=True)  # Username who filled the field
    field_value = db.Column(db.Text, nullable=False)  # The text value entered
    filled_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))  # IP address when filled (for audit)
    user_agent = db.Column(db.String(500), nullable=True)  # Browser user agent
    
    # Relationships
    document = db.relationship('Document', backref='typed_field_values')
    typed_field = db.relationship('DocumentTypedField', backref='values')
    
    def __repr__(self):
        return f'<DocumentTypedFieldValue {self.id} by {self.username} on Field {self.typed_field_id}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'typed_field_id': self.typed_field_id,
            'username': self.username,
            'field_value': self.field_value,
            'filled_at': self.filled_at.isoformat() if self.filled_at else None
        }


class DocumentAssignment(db.Model):
    """Track which documents are assigned to which users for signing"""
    __tablename__ = 'document_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    username = db.Column(db.String(100), nullable=False, index=True)  # User assigned to sign
    assigned_by = db.Column(db.String(100))  # Admin who assigned it
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.Date)  # Optional due date
    is_completed = db.Column(db.Boolean, default=False)  # True when all required fields are signed
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)  # Optional notes
    
    # Relationships
    document = db.relationship('Document', backref='assignments')
    
    def __repr__(self):
        return f'<DocumentAssignment {self.document_id} to {self.username} ({self.is_completed})>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'document_id': self.document_id,
            'username': self.username,
            'assigned_by': self.assigned_by,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'is_completed': self.is_completed,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'notes': self.notes
        }


class ExternalLink(db.Model):
    """External links that admins can add for users to see on their dashboard"""
    __tablename__ = 'external_links'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(100), default='🔗')  # Emoji or icon identifier
    image_filename = db.Column(db.String(255))  # Filename of uploaded image
    order = db.Column(db.Integer, default=0)  # Display order
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.String(100))  # Username of admin who created it
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ExternalLink {self.title} ({self.url})>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'description': self.description,
            'icon': self.icon,
            'image_filename': self.image_filename,
            'order': self.order,
            'is_active': self.is_active,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UserNotification(db.Model):
    """Track which notifications users have viewed"""
    __tablename__ = 'user_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, index=True)
    notification_type = db.Column(db.String(50), nullable=False)  # 'training', 'task', 'document'
    notification_id = db.Column(db.String(200), nullable=False)  # ID of the item (video_id, task_id, doc_id)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicates
    __table_args__ = (db.UniqueConstraint('username', 'notification_type', 'notification_id', name='unique_user_notification'),)
    
    def __repr__(self):
        return f'<UserNotification {self.username} - {self.notification_type}:{self.notification_id} ({self.is_read})>'


class AdminSetting(db.Model):
    """Key-value store for admin defaults (e.g. default finale message)."""
    __tablename__ = 'admin_settings'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<AdminSetting {self.key}>'


class Store(db.Model):
    """Store/location for manager-scoped onboarding."""
    __tablename__ = 'stores'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)

    def __repr__(self):
        return f'<Store {self.name}>'


class ManagerPermission(db.Model):
    """Per-user manager permission keys (e.g. edit_new_hire, revoke_access)."""
    __tablename__ = 'manager_permissions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    permission_key = db.Column(db.String(80), nullable=False)

    def __repr__(self):
        return f'<ManagerPermission user_id={self.user_id} {self.permission_key}>'


# Association: which documents are visible to which stores (empty = all stores)
document_stores = db.Table('document_stores',
    db.Column('document_id', db.Integer, db.ForeignKey('documents.id'), primary_key=True),
    db.Column('store_id', db.Integer, db.ForeignKey('stores.id'), primary_key=True)
)

