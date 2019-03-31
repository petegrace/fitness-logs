from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from flask_mail import Message
from werkzeug.urls import url_parse
from app.auth import bp
from app.auth.forms import LoginForm, RegisterForm, PreferencesForm, ResetPasswordForm
from app.auth.common import configured_google_client
from app.models import User, ExerciseForToday, ActivityForToday
from app import db, app, mail
from requests_oauth2.services import GoogleClient
from requests_oauth2 import OAuth2BearerToken
from datetime import datetime, date, timedelta
from threading import Thread
import requests
import json
import calendar


# Helpers
google_auth = configured_google_client()

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)
	
def register_user(user):
	db.session.add(user)
	db.session.commit()
	flash("Congratulations! You are now a registered user of Training Ticks")
	login_user(user)

	# Send confirmation email
	msg = Message(subject="Registration Confirmation",
		   		  sender=("Training Ticks", "welcome@trainingticks.com"),
		   		  recipients=[user.email])

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

	return redirect(url_for("index", is_new_user=True))

@bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
	if current_user.is_authenticated:
		return redirect(url_for("index"))

	user = User.verify_reset_password_token(token)
	if not user:
		return redirect(url_for("index"))

	form = ResetPasswordForm()
	if form.validate_on_submit():
		user.password_hash = User.generate_hash(form.password.data)
		db.session.commit()
		flash("Password has been reset. Please login from the home page.")

	return render_template("auth/reset_password.html", form=form)



@bp.route("/react_login")
def react_login():
	return render_template("auth/react_login.html")

# Routes
@bp.route("/login")
def login():
	return render_template("auth/react_login.html")


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
		if "email" in session:
			del session["email"]
			session.modified = True

	logout_user()
	return redirect(url_for("index"))


@bp.route("/preferences", methods=['GET', 'POST'])
@login_required
def preferences():
	preferences_form = PreferencesForm()

	if preferences_form.validate_on_submit():
		current_user.is_opted_in_for_marketing_emails = preferences_form.opt_in_to_marketing_emails.data
		db.session.commit()
		flash("Your user preferences have been changed.")

	# If it's a get...
	preferences_form.opt_in_to_marketing_emails.data = current_user.is_opted_in_for_marketing_emails
	return render_template("auth/preferences.html", title="Preferences", form=preferences_form)

@bp.route("/test_email")
def test_email():
	msg = Message(subject="Registration Confirmation",
		   		  sender=("Training Ticks", "welcome@trainingticks.com"),
		   		  recipients=["pete@trainingticks.com"])

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

	return redirect(url_for("index"))