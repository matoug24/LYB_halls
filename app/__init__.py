import os
from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_talisman import Talisman
from flask_caching import Cache

db = SQLAlchemy()
login_manager = LoginManager()
cache = Cache()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Ensure the upload folder exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    cache.init_app(app)
    Talisman(app, content_security_policy=None)
    
    from app.routes import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    with app.app_context():
        db.create_all()
        # Create default superadmin if not present
        from app.models import User
        # admin_user = User.query.filter_by(username="superadmin").first()
        admin_exists = db.session.query(User.query.filter_by(username="superadmin").exists()).scalar()

        if not admin_exists:
            print("Creating default superadmin user...")
            admin_user = User(username="superadmin", is_site_admin=True)
            admin_user.set_password("Admin123-%")  # Use a secure password
            db.session.add(admin_user)
            db.session.commit()
            print("Superadmin user created successfully!")
        else:
            print("Superadmin user already exists.")
    return app
