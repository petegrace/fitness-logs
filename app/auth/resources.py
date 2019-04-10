from flask import make_response, flash, session, url_for
from flask_login import login_user
from flask_restful import Resource, reqparse, inputs
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, jwt_refresh_token_required, get_jwt_identity, get_raw_jwt
from flask_mail import Message
from app import app, db, mail, training_plan_utils
from app.models import User
from requests_oauth2 import OAuth2BearerToken
from datetime import datetime, timedelta, date
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
        parser.add_argument("authType", help="Whether the authentication method is via Google or direct", required=True)
        parser.add_argument("google_access_token", help="Must supply an access token for Google auth")
        parser.add_argument("email", help="Email address used to login, only supplied for direct auth")
        parser.add_argument("password", help="Only required for direct authentication")
        data = parser.parse_args()

        # 1. Get the google user using the google_access_token we now have
        if data["authType"] == "Google":
            with requests.Session() as s:
                s.auth = OAuth2BearerToken(data["google_access_token"])
                discovery_request = s.get("https://accounts.google.com/.well-known/openid-configuration")
                discovery_request.raise_for_status()
                userinfo_endpoint = discovery_request.json()["userinfo_endpoint"]

                userinfo_request = s.get(userinfo_endpoint)
                userinfo_request.raise_for_status()
                user_email = userinfo_request.json()["email"]
        else:
            user_email = data["email"]

        # 2. Lookup the user in our DB, and redirect to registration if we can't find them
        current_user = User.query.filter_by(email=user_email).first()
        
        is_authenticated = False
        if data["authType"] == "Google" and current_user:
            is_authenticated = True
        elif data["authType"] == "direct" and current_user:
            is_authenticated = current_user.verify_password(data["password"])

        if not is_authenticated:
             return { 
                 "email": user_email,
                 "message": "No user found or password incorrect. Please register or try again"
              }, 401  # 401 for unauthorized to indicate they need to register
        else:
            # 3. Create access token (with 60-min expiry)
            access_token = create_access_token(identity=current_user.id, expires_delta=timedelta(minutes=60))

            # 4. do the loginmanager stuff that we need to keep
            login_user(current_user) # From the flask_login library, does the session management bit

            
            # Run some application stuff to set things up
            if current_user.last_login_date != datetime.date(datetime.today()):
                training_plan_utils.refresh_plan_for_today(current_user)
                
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
        parser.add_argument("authType", help="Whether the authentication is using Google account or direct with Training Ticks", required=True)
        parser.add_argument("email", help="Email address used to login, which is used for both Google and direct auth", required=True)
        parser.add_argument("password", help="Only required for direct authentication")
        parser.add_argument("first_name", help="First name of the user who is registering, only required for direct authentication at present")
        parser.add_argument("last_name", help="Surname of the user who is registering, only required for direct authentication at present")
        parser.add_argument("opt_in_to_marketing_emails", help="Flag to indicate if the user wants to receive email updates", type=inputs.boolean)
        data = parser.parse_args()

        # 2. Validate for an existing user with same email
        existing_user = User.query.filter_by(email=data["email"]).first()
        if existing_user:
            return {
                    "message": "Email address is already registered."
            }, 409 # conflict status code

        # 2. Add new user
        new_user = User(email=data["email"],
						auth_type=data["authType"],
                        password_hash=User.generate_hash(data["password"]),
                        first_name=data["first_name"],
                        last_name=data["last_name"],
						is_opted_in_for_marketing_emails=data["opt_in_to_marketing_emails"])
        db.session.add(new_user)
        db.session.commit()

        # 3. Create access token
        access_token = create_access_token(identity=new_user.id, expires_delta=timedelta(minutes=60))

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
                    
                    <p>Training Ticks started off as a personal side-project that I initially created to serve my own training needs, and it's still very early days in the journey
                    to build a product that serves everyone else's requirements. I'm adding and improving features all the time, so bear with me if some things look a little limited or rough around the edges.</p>
                    
                    <p>I'm really keen to get as much feedback as possible from our early users,
                    so drop us a quick email to <a href="mailto:feedback@trainingticks.com">feedback@trainingticks.com</a> if you’ve got any suggestions,
                    ideas or comments - positive or negative.</p>

                    <p>In particular if you didn’t find exactly what you were looking for, please let me know as it might be something I can build in… just as I’ve been doing for the small group of users who’ve
                    fed back so far. You can also take a look at our
                    <a href="https://trello.com/b/44rh6f3e/training-ticks-public-roadmap">Public Roadmap</a> to see what's on the horizon,
                    where you can comment and vote on any features or ideas you're particularly keen on.</p>
                    
                    <p>In the meantime I hope that you find Training Ticks useful to assist your training, and best of luck with your next race or challenge.</p>

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

class ResetPasswordRequest(Resource):
    def post(self):
        # 1. retrieve the body from the post
        parser = reqparse.RequestParser()
        parser.add_argument("email", help="Email address used to login, only supplied for direct auth")
        data = parser.parse_args()

        # 2. Lookup the user in our DB, and return unauthorised if we can't find them or not using direct auth
        existing_user = User.query.filter_by(email=data["email"]).first()
        
        if (not existing_user) or (existing_user.auth_type != "direct"):
            return { 
                 "message": "Cannot reset password for email provided"
              }, 401

        # 3. Send the email
        reset_token = existing_user.get_reset_password_token()
        msg = Message(subject="Reset Password",
		   		  sender=("Training Ticks", "support@trainingticks.com"),
		   		  recipients=[existing_user.email])

        msg.html = """
                    <h1>Reset Password for Training Ticks</h1>
				
                    <p><a href={url}">Click here</a> to reset your password for Training Ticks.</p>
                    
                    <p>Or you can paste the following link into your browser's address bar:</p>

                    <p>{url}</p>
                    
                    <p>If you've not chosen to reset your password and weren't expecting this email please let us know at support@trainingticks.com.</p>

                    <p>Thanks,</p>

                    <p>Training Ticks Support</p>
                """.format(url=url_for("auth.reset_password", token=reset_token, _external=True))

        # Send the mail asynchronously from separate thread
        Thread(target=send_async_email, args=(app, msg)).start()

        return "", 204 # Report back success

        

# TODO: Consider if this is worthwhile or if we just go with a short-lived (e.g. 60 mins) access token, not using it currently
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

class UserInfo(Resource):
    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))
        today = date.today()

        user_info = {
            "distance_uom_preference": current_user.distance_uom_preference if current_user.distance_uom_preference else "km",
            "has_flexible_planning_enabled": current_user.has_weekly_flexible_planning_enabled,
            "has_planned_activity_for_today": current_user.has_planned_activity_for_day(today)
        }

        return {
            "user_info": user_info
        }, 200

    @jwt_required
    def patch(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("distance_uom_preference", help="Whether the user wants to see distances in km or miles")
        parser.add_argument("has_flexible_planning_enabled", help="Whether the user has enabled the ability to plan activities and exercises for a week without having to choose a day")
        data = parser.parse_args()

        print(data["has_flexible_planning_enabled"])

        current_user.distance_uom_preference = data["distance_uom_preference"]
        current_user.has_weekly_flexible_planning_enabled = True if data["has_flexible_planning_enabled"] == "True" else False

        db.session.commit()
        
        updated_user_info = {
            "distance_uom_preference": current_user.distance_uom_preference,
            "has_flexible_planning_enabled": current_user.has_weekly_flexible_planning_enabled
        }

        print(updated_user_info)

        return {
            "updated_user_info": updated_user_info
        }, 200
