import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-super-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///qrcode_app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload setngs
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    QR_CODES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'qr_codes')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Encryption key for QR data (Fernet)
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY') or 'ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg='
