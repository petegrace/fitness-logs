from flask import Flask, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from config import Config
from oauth2client.contrib.flask_util import UserOAuth2
import httplib2
import json

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = "auth.login"
bootstrap = Bootstrap(app)
moment = Moment(app)
oauth2 = UserOAuth2()

from app.auth import bp as auth_bp
app.register_blueprint(auth_bp, url_prefix="/auth")

from app import routes, models, dataviz


# Google Auth initialization
def _request_user_info(credentials):
	http = httplib2.Http()
	credentials.authorize(http)
	resp, content = http.request("https://www.googleapis.com/plus/v1/people/me")
	session['google_profile'] = json.loads(content.decode('utf-8'))

# Initalize the OAuth2 helper.
oauth2.init_app(app,
    			scopes=['email', 'profile'],
    			authorize_callback=_request_user_info)
# End of Google Auth stuff