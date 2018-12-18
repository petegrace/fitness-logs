from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import db, oauth2
from app.auth import bp
from app.auth.forms import LoginForm, RegisterForm
from app.models import User


# Helpers
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
		new_user = User(email=session['google_profile']['emails'][0]['value'], auth_type="Google")
		register_user(new_user)

	if 'google_profile' in session:
		google_email = session['google_profile']['emails'][0]['value'] # TODO: This might be a bit risky for if linked accounts
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
	return render_template("auth/login.html", title="Sign In")#, form=form)


@bp.route("/cancel")
def cancel():
	if 'google_profile' in session:
		# Delete the user's profile and the credentials stored by oauth2.
		del session['google_profile']
		session.modified = True
		oauth2.storage.delete()

	return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
	if current_user.auth_type == "Google":
		# Delete the user's profile and the credentials stored by oauth2.
		del session['google_profile']
		session.modified = True
		oauth2.storage.delete()

	logout_user()
	return redirect(url_for("index"))

@bp.route("/register")
def register():
	form = RegisterForm()
	form.google_email = "test@gmail.com"
	return render_template("auth/register.html", title="Complete Registration", form=form)

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