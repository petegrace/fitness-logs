from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db #, oauth2
from app.auth import bp
from app.auth.forms import LoginForm, RegisterForm
from app.models import User
from requests_oauth2.services import GoogleClient
from requests_oauth2 import OAuth2BearerToken
import requests
import json


# Helpers
google_auth = GoogleClient(
	client_id = app.config["GOOGLE_OAUTH2_CLIENT_ID"],
	client_secret=app.config["GOOGLE_OAUTH2_CLIENT_SECRET"],
	redirect_uri="http://localhost:5000/auth/oauth2callback",
)

def register_user(user):
	db.session.add(user)
	db.session.commit()
	flash("Congratulations! You are now a registered user of Training Ticks")
	login_user(user)
	return redirect(url_for("index"))


# Routes
@bp.route("/login", methods=['GET', 'POST'])
def login():
	# Send an already logged in user back to the index
	if current_user.is_authenticated:
		return redirect(url_for("index"))

	register_form = RegisterForm()

	if register_form.validate_on_submit():
		new_user = User(email=session["email"], auth_type="Google")
		register_user(new_user)

	if "email" in session:
		google_email = session["email"] 
		user = User.query.filter_by(email=google_email).first()

		if user is None:
			register_form.google_email = google_email
			return render_template("auth/register.html", title="Complete Registration", form=register_form)			
		else:
			login_user(user)
			# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
			next_page = request.args.get("next")
			if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
				return redirect(url_for("index"))
			return redirect(next_page)

	# for the get...
	authorization_url = google_auth.authorize_url(
	    scope=["email"],
		response_type="code",
	)
	return render_template("auth/login.html", title="Sign In", authorization_url=authorization_url)#, form=form)


@bp.route("/oauth2callback")
def oauth2callback():
	code = request.args.get("code")
	error = request.args.get("error")
	if error:
	    return "error :( {!r}".format(error)
	if not code:
	    return redirect(google_auth.authorize_url(
	        scope=["email"],
	        response_type="code",
	    ))

	data = google_auth.get_token(
	    code=code,
	    grant_type="authorization_code",
	)

	with requests.Session() as s:
		s.auth = OAuth2BearerToken(data["access_token"])
		discovery_request = s.get("https://accounts.google.com/.well-known/openid-configuration")
		discovery_request.raise_for_status()
		userinfo_endpoint = discovery_request.json()["userinfo_endpoint"]

		userinfo_request = s.get(userinfo_endpoint)
		userinfo_request.raise_for_status()

	session["email"] = userinfo_request.json()["email"]
	return redirect(url_for("auth.login"))


@bp.route("/cancel")
def cancel():
	if "email" in session:
		# Delete the user's profile and the credentials stored by oauth2.
		del session["email"]
		session.modified = True

	return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
	if current_user.auth_type == "Google":
		# Delete the user's profile and the credentials stored by oauth2.
		del session["email"]
		session.modified = True

	logout_user()
	return redirect(url_for("index"))

# @bp.route("/register", methods=["GET", "POST"])
# def register():
# 	# Send an already logged in user back to the index
# 	if current_user.is_authenticated:
# 		return redirect(url_for("index"))

# 	form = RegistrationForm()

# 	# for the post, create the user, log them in and redirect
# 	if form.validate_on_submit():
# 		user = User(email=form.email.data)
# 		user.set_password(form.password.data)
# 		register_user(user)

# 	# for the get...
# 	return render_template("auth/register.html", title="Register", form=form)