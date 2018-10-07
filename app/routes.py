from datetime import datetime
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db
from app.forms import LoginForm, RegistrationForm, LogNewExerciseTypeForm
from app.models import User, ExerciseType, Exercise

@app.route("/")
@app.route("/index")
@login_required
def index():
	page = request.args.get("page", 1, type=int)
	exercises = current_user.exercises().paginate(page, app.config["EXERCISES_PER_PAGE"], False) # Pagination object
	next_url = url_for("index", page=exercises.next_num) if exercises.has_next else None
	prev_url = url_for("index", page=exercises.prev_num) if exercises.has_prev else None
	exercise_types = current_user.exercise_types
	return render_template("index.html", title="Home", exercises=exercises.items, exercise_types=exercise_types,
							next_url=next_url, prev_url=prev_url)


@app.route("/login", methods=["GET", "POST"])
def login():
	# Send an already logged in user back to the index
	if current_user.is_authenticated:
		return redirect(url_for("index"))

	form = LoginForm()

	# for the post...
	if form.validate_on_submit():
		#Attempt to lookup the user in the DB
		user = User.query.filter_by(email=form.email.data).first()

		# Handle no match on user name and then check the password
		if user is None or not user.check_password(form.password.data):
			flash("Incorrect user name or password")
			return redirect(url_for("login"))

		# If we've reached here then we can log the user in and redirect back to index
		login_user(user)

		# Redirect to the page the user came from if it was passed in as next parameter, otherwise the index
		next_page = request.args.get("next")
		if not next_page or url_parse(next_page).netloc != "": # netloc check prevents redirection to another website
			return redirect(url_for("index"))
		return redirect(next_page)

	# for the get...
	return render_template("login.html", title="Sign In", form=form)


@app.route("/logout")
def logout():
	logout_user()
	return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
	# Send an already logged in user back to the index
	if current_user.is_authenticated:
		return redirect(url_for("index"))

	form = RegistrationForm()

	# for the post, create the user, log them in and redirect
	if form.validate_on_submit():
		user = User(email=form.email.data)
		user.set_password(form.password.data)
		db.session.add(user)
		db.session.commit()
		flash("Congratulations! You are now a registered user")
		login_user(user)
		return redirect(url_for("index"))

	# for the get...
	return render_template("register.html", title="Register", form=form)


@app.route("/new_exercise", methods=["GET", "POST"])
@login_required
def new_exercise():
	form = LogNewExerciseTypeForm()

	# for the post...
	if form.validate_on_submit():
		exercise_type = ExerciseType(name=form.name.data,
									 owner=current_user,
									 measured_by="reps",
									 default_reps=form.reps.data)
		db.session.add(exercise_type)
		exercise = Exercise(type=exercise_type,
							exercise_datetime=form.exercise_datetime.data,
							reps=form.reps.data)		
		db.session.add(exercise)
		db.session.commit()
		flash("Added {type} at {datetime}".format(type=exercise_type.name, datetime=exercise.exercise_datetime))
		return redirect(url_for("index"))

	#for the get...
	return render_template("new_exercise.html", title="Log New Exercise Type", form=form)

@app.route("/log_exercise/<id>")
@login_required
def log_exercise(id):
	exercise_type = ExerciseType.query.get(int(id))

	# Log the exercise based on defaults
	# TODO: This should be a function somewhere to avoid duplication with new_exercise, just not sure where yet!
	exercise = Exercise(type=exercise_type,
						exercise_datetime=datetime.utcnow(),
						reps=exercise_type.default_reps)
	db.session.add(exercise)
	db.session.commit()
	flash("Added {type} at {datetime}".format(type=exercise_type.name, datetime=exercise.exercise_datetime))
	return redirect(url_for("index"))