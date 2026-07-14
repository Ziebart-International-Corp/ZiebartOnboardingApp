"""Upload filename allow-lists."""
from __future__ import annotations

from flask import current_app


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def allowed_video_file(filename):
    """Check if video file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_VIDEO_EXTENSIONS']
