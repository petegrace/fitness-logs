from flask import make_response, flash
from flask_login import login_user
from flask_restful import Resource, reqparse, inputs
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, jwt_refresh_token_required, get_jwt_identity, get_raw_jwt
from flask_mail import Message
from app import app, db, mail
from app.models import User
from requests_oauth2 import OAuth2BearerToken
from datetime import datetime, timedelta
from threading import Thread
import requests
import json

#Helpers
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

#Resources
class UserLogin(Resource):
    def post(self):
        # 1. retrieve the body from the post that should include an access token for google auth
        parser = reqparse.RequestParser()
        parser.add_argument("google_access_token", help="Must supply an access token for Google auth", required=True)
        data = parser.parse_args()

        # 1. Get the google user using the google_access_token we now have
        with requests.Session() as s:
            s.auth = OAuth2BearerToken(data["google_access_token"])
            discovery_request = s.get("https://accounts.google.com/.well-known/openid-configuration")
            discovery_request.raise_for_status()
            userinfo_endpoint = discovery_request.json()["userinfo_endpoint"]

            userinfo_request = s.get(userinfo_endpoint)
            userinfo_request.raise_for_status()
            user_email = userinfo_request.json()["email"]

        # 2. Lookup the user in our DB, and redirect to registration if we can't find them
        current_user = User.query.filter_by(email=user_email).first()

        if not current_user:
             return { 
                 "google_email": user_email,
                 "message": "No user found. Please register"
              }, 401  # 401 for unauthorized to indicate they need to register
        else:
            # 3. Create access token (with 60-min expiry)
            access_token = create_access_token(identity=user_email, expires_delta=timedelta(minutes=60))

            # 4. do the loginmanager stuff that we need to keep
            login_user(current_user) # From the flask_login library, does the session management bit
            
            # Run some application stuff to set things up
            if current_user.last_login_date != datetime.date(datetime.today()):
                training_plan.refresh_plan_for_today(current_user)
                
            current_user.last_login_datetime = datetime.utcnow()
            db.session.commit()

        # 5. return email and access token
        return {
             "user_email": user_email,
             "user_id": current_user.id,
             "status": "signed in"
        }, 201, {
            "x-auth-token": access_token # we have to expose this header in the CORS configuration in __init__
        }

class UserLogoutAccess(Resource):
    def post(self):
        return { "message": "User logout" }

class UserLogoutRefresh(Resource):
    def post(self):
        return { "message": "User logout" }

class RegisterUser(Resource):
    def post(self):
        # 1. Retrieve the body
        parser = reqparse.RequestParser()
        parser.add_argument("email", help="Must supply an email address to register", required=True)
        parser.add_argument("opt_in_to_marketing_emails", type=inputs.boolean)
        data = parser.parse_args()

        # 2. Add new user
        new_user = User(email=data["email"],
						auth_type="Google",
						is_opted_in_for_marketing_emails=data["opt_in_to_marketing_emails"])
        db.session.add(new_user)
        db.session.commit()

        # 3. Create access token
        access_token = create_access_token(identity=new_user.email, expires_delta=timedelta(minutes=60))

        # 4. Do the loginmanager thing and flash for the non-react bits
        flash("Congratulations! You are now a registered user of Training Ticks") # not sure if this would work
        login_user(new_user) # From the flask_login library, does the session management bit

        # 5. Send confirmation email
        msg = Message(subject="Registration Confirmation",
		   		  sender=("Training Ticks", "welcome@trainingticks.com"),
		   		  recipients=[new_user.email])

        msg.html = """
                    <h1>Welcome to Training Ticks</h1>
                    
                    <p>Thanks for registering with <a href="https://www.trainingticks.com">Training Ticks</a>, and welcome to our community of runners and other athletes looking to
                    improve their training, set motivating goals, and smash their PB’s!</p>
                    
                    <p>It’s still really early days in our journey and we’re making new features available every week,
                    so bear with us if some things look a little rough around the edges.</p>
                    
                    <p>We’re really keen to get as much feedback as possible from our early users,
                    so drop us a quick email to <a href="mailto:feedback@trainingticks.com">feedback@trainingticks.com</a> if you’ve any suggestions,
                    ideas or comments - positive or negative.</p>

                    <p>In particular if you didn’t find exactly what you were looking for, please let us know as it might be something we can build in…
                    just as we’ve done for the small group of friends and family users who’ve fed back up to now.</p>
                    
                    <p>In the meantime we hope that you find Training Ticks useful to assist your trading,
                    and go well with whatever your next race or challenge is going to be.</p>

                    <p>Happy running!</p>

                    <p>Pete<br />
                    <a href="https://www.trainingticks.com">Training Ticks</a></p>
                """

        # Send the mail asynchronously from separate thread
        Thread(target=send_async_email, args=(app, msg)).start()

        # 6. Return same response as we'd do with a login
        return {
             "user_email": data["email"],
             "user_id": new_user.id,
             "status": "signed in"
        }, 201, {
            "x-auth-token": access_token # we have to expose this header in the CORS configuration in __init__
        }


# TODO: Consider if this is worthwhile or if we just go with a short-lived (e.g. 60 mins) access token
class TokenRefresh(Resource):
    @jwt_refresh_token_required
    def post(self):
        current_user_email = get_jwt_identity()
        access_token = create_access_token(identity=current_user_email)
        return { "access_token": access_token }

class CheckToken(Resource):
    @jwt_required
    def get(self):
        return { "result": "valid" }