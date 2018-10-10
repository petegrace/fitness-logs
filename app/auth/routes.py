from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import db, oauth2
from app.auth import bp
from app.auth.forms import LoginForm, RegistrationForm
from app.models import User


# Helpers
def register_user(user):
	db.session.add(user)
	db.session.commit()
	flash("Congratulations! You are now a registered user")
	login_user(user)
	return redirect(url_for("index"))


# Routes
@bp.route("/login") # Taken out , methods=["GET", "POST"]
def login():
	# Send an already logged in user back to the index
	if current_user.is_authenticated:
		return redirect(url_for("index"))

	if 'google_profile' in session:
		google_email = session['google_profile']['emails'][0]['value'] # TODO: This might be a bit risky for if linked accounts
		user = User.query.filter_by(email=google_email).first()

		if user is None:
			new_user = User(email=google_email, auth_type="Google")
			register_user(new_user)
		else:
			login_user(user)

			# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
			next_page = request.args.get("next")
			if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
				return redirect(url_for("index"))
			return redirect(next_page)

	#form = LoginForm()

	# for the post...
	# if form.validate_on_submit():
	# 	#Attempt to lookup the user in the DB
	# 	user = User.query.filter_by(email=form.email.data).first()

	# 	# Handle no match on user name and then check the password
	# 	if user is None or not user.check_password(form.password.data):
	# 		flash("Incorrect user name or password")
	# 		return redirect(url_for("auth.login"))

	# 	# If we've reached here then we can log the user in and redirect back to index
	# 	login_user(user)

	# 	# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
	# 	next_page = request.args.get("next")
	# 	if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
	# 		return redirect(url_for("index"))
	# 	return redirect(next_page)

	# for the get...
	return render_template("auth/login.html", title="Sign In")#, form=form)


@bp.route("/logout")
def logout():
	if current_user.auth_type == "Google":
		# Delete the user's profile and the credentials stored by oauth2.
		del session['google_profile']
		session.modified = True
		oauth2.storage.delete()

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