from flask import Flask, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_talisman import Talisman
from flask_mail import Mail
from flask_restful import Api
from flask_jwt_extended import JWTManager
from flask_cors import CORS
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
mail = Mail(app)
api = Api(app)
jwt = JWTManager(app)
cors = CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}}, expose_headers=["x-auth-token"])

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

from app.blog import bp as blog_bp
app.register_blueprint(blog_bp, url_prefix="/blog")

from app import routes, models, errors, app_classes, dataviz, utils, analysis

# TODO: Would be good to have these as part of the auth blueprint still (or even their own blueprint) but don't want to deviate from tutorial too much!
api.add_resource(auth.resources.UserLogin, "/api/login")
api.add_resource(auth.resources.UserLogoutAccess, "/api/logout/access")
api.add_resource(auth.resources.UserLogoutRefresh, "/api/logout/refresh")
api.add_resource(auth.resources.TokenRefresh, "/api/token/refresh")
api.add_resource(auth.resources.SecretResource, "/api/secret")