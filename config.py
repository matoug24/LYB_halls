import os
from datetime import timedelta

class Config:
    SECRET_KEY = 'your-secret-key'  # Change for production!
    SQLALCHEMY_DATABASE_URI = 'sqlite:///halls.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'app', 'static', 'uploads', 'halls')
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
