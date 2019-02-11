from flask import make_response
from flask_restful import Resource, reqparse
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, jwt_refresh_token_required, get_jwt_identity, get_raw_jwt
from app.models import User
from requests_oauth2 import OAuth2BearerToken
from datetime import timedelta
import requests
import json

parser = reqparse.RequestParser()
parser.add_argument("google_access_token", help="Must supply an access token for Google auth", required=True)

# TODO: for first iteration we'd want to hit this endpoint from within our existing login handling, probably without the need to lookup to DB again
class UserLogin(Resource):
    def post(self):
        # 1. retrieve the body from the post that should include an access token for google auth
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
             return { "message": "No user with email of {email}".format(email=user_email) }
        else:
            # 3. Create access token (with 60-min expiry)
            access_token = create_access_token(identity=user_email, expires_delta=timedelta(minutes=60))

        # 4. go and do the loginmanager stuff that we need to keep
        # 5. return email and access token
        return {
             "user_email": user_email,
             "user_id": current_user.id,
             "status": "signed in"
        }, 201, {
            "x-auth-token": access_token # we have to expose this header in the CORS configuration in __init__
        }

        # if not current_user:
        #     return { "message": "No user with email of {email}".format(email=data["email"]) }
        # else:
        #     access_token = create_access_token(identity=current_user.email)
        #     refresh_token = create_refresh_token(identity=current_user.email)
        #     return { 
        #         "message": "Logged in as {email}".format(email=current_user.email),
        #         "access_token": access_token,
        #         "refresh_token": refresh_token
        #     }

class UserLogoutAccess(Resource):
    def post(self):
        return { "message": "User logout" }

class UserLogoutRefresh(Resource):
    def post(self):
        return { "message": "User logout" }

# TODO: Consider if this is worthwhile or if we just go with a short-lived (e.g. 60 mins) access token
class TokenRefresh(Resource):
    @jwt_refresh_token_required
    def post(self):
        current_user_email = get_jwt_identity()
        access_token = create_access_token(identity=current_user_email)
        return { "access_token": access_token }

class SecretResource(Resource):
    @jwt_required
    def get(self):
        return { "answer": 42 }