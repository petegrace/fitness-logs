from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db #, oauth2
from app.auth import bp
from app.auth.forms import LoginForm, RegisterForm
from app.auth.common import configured_google_client
from app.models import User, ExerciseForToday
from requests_oauth2.services import GoogleClient
from requests_oauth2 import OAuth2BearerToken
from datetime import datetime, date, timedelta
import requests
import json
import calendar


# Helpers
google_auth = configured_google_client()
	
def register_user(user):
	db.session.add(user)
	db.session.commit()
	flash("Congratulations! You are now a registered user of Training Ticks")
	login_user(user)
	return redirect(url_for("index", is_new_user=True))


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
			login_user(user) # From the flask_login library, does the session management bit

			# Run some application stuff to set things up (TODO: Probably doesn't belong in Auth, can refator later)...
			today = date.today()
			current_day = calendar.day_abbr[today.weekday()]

			if current_user.last_login_date != datetime.date(datetime.today()):
				# Clear out the exercises for today and reload
				for exercise_for_today in current_user.exercises_for_today():
					db.session.delete(exercise_for_today)

				for scheduled_exercise in current_user.scheduled_exercises(scheduled_day=current_day):
					new_exercise_for_today = ExerciseForToday(scheduled_exercise_id = scheduled_exercise.id)
					db.session.add(new_exercise_for_today)

				db.session.commit()

			current_user.last_login_datetime = datetime.utcnow()
			db.session.commit()

			# If the user hasn't activated any features yet then we want to encourage them...
			if not current_user.is_activated_user:
				return redirect(url_for("index", is_new_user=True))
			return redirect(url_for("index"))

	# for the get...
	authorization_url = google_auth.authorize_url(
	    scope=["email"],
		response_type="code",
	)
	return render_template("auth/login.html", title="Sign In", authorization_url=authorization_url)


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