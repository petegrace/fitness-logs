from datetime import datetime
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_user, logout_user, login_required
from werkzeug.urls import url_parse
from app import app, db
from app.forms import LogNewExerciseTypeForm, EditExerciseForm
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


@app.route('/edit_exercise/<id>', methods=['GET', 'POST'])
@login_required
def edit_exercise(id):
    form = EditExerciseForm()
    exercise = Exercise.query.get(int(id))

    if form.validate_on_submit():
        exercise.exercise_datetime = form.exercise_datetime.data
        exercise.reps = form.reps.data
        db.session.commit()
        flash("Updated {type} at {datetime}".format(type=exercise.type.name, datetime=exercise.exercise_datetime))
        return redirect(url_for("index"))
    elif request.method == 'GET':
        form.exercise_datetime.data = exercise.exercise_datetime
        form.reps.data = exercise.reps
    return render_template("edit_exercise.html", title="Edit Exercise", form=form, exercise_name=exercise.type.name)