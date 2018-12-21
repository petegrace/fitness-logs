from flask import Flask, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_sslify import SSLify
from config import Config
import httplib2
import json

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = "auth.login"
login.login_message = None
sslify = SSLify(app)
bootstrap = Bootstrap(app)
moment = Moment(app)

from app.auth import bp as auth_bp
app.register_blueprint(auth_bp, url_prefix="/auth")

from app import routes, models, errors, app_classes, dataviz, utils, analysis