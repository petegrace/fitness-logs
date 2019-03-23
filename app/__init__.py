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
from datetime import timedelta
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
cors = CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "https://trainingticks.com", "https://www.trainingticks.com"]}}, expose_headers=["x-auth-token"])

@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=60)

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
    'img-src': ['*',
                'data:'
    ],
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

from app import routes, resources, models, errors, app_classes, dataviz, utils, analysis, ga, training_plan_utils

# TODO: Would be good to have these as part of the auth blueprint still (or even their own blueprint) but don't want to deviate from tutorial too much!
api.add_resource(auth.resources.UserLogin, "/api/login")
api.add_resource(auth.resources.UserLogoutAccess, "/api/logout/access")
api.add_resource(auth.resources.UserLogoutRefresh, "/api/logout/refresh")
api.add_resource(auth.resources.TokenRefresh, "/api/token/refresh")
api.add_resource(auth.resources.CheckToken, "/api/check_token")
api.add_resource(auth.resources.RegisterUser, "/api/register")
api.add_resource(auth.resources.UserInfo, "/api/user_info")

api.add_resource(resources.AnnualStats, "/api/annual_stats")
api.add_resource(resources.ActivityTypes, "/api/activity_types")
api.add_resource(resources.PlannedActivities, "/api/planned_activities")
api.add_resource(resources.PlannedActivity, "/api/planned_activity/<planned_activity_id>")
api.add_resource(resources.PlannedExercises, "/api/planned_exercises")
api.add_resource(resources.PlannedExercise, "/api/planned_exercise/<planned_exercise_id>")

api.add_resource(resources.TrainingPlanTemplates, "/api/training_plan_templates")