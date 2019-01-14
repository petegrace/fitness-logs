from flask import Flask, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_talisman import Talisman
from config import Config
import json

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = "auth.login"
login.login_message = None
bootstrap = Bootstrap(app)
moment = Moment(app)

# TODO: Make these more specific and avoid the inline stuff
csp = {
    'default-src': [
        '*'
    ],
    'style-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        '*'
    ],
    'img-src': '*',
    'script-src': [
        '\'self\'',
        '\'unsafe-inline\'',
        '\'unsafe-eval\'',
        '*'
    ]
}
talisman = Talisman(app, content_security_policy=csp)

from app.auth import bp as auth_bp
app.register_blueprint(auth_bp, url_prefix="/auth")

from app import routes, models, errors, app_classes, dataviz, utils, analysis