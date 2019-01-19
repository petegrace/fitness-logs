from app import app, db
from app.models import User, ExerciseForToday, ActivityForToday

# TODO: Needs some thought to make sure we don't clear out activities that are actually for today
def refresh_plan_for_today(user):   
    # Clear out the activities for today and reload
    for activity_for_today in user.activities_for_today():
        db.session.delete(activity_for_today)

    for scheduled_activity in user.scheduled_activities_filtered(scheduled_day=current_day):
        new_activity_for_today = ActivityForToday(scheduled_activity_id = scheduled_activity.id)
        db.session.add(new_activity_for_today)

    # Clear out the exercises for today and reload
    for exercise_for_today in user.exercises_for_today():
        db.session.delete(exercise_for_today)

    for scheduled_exercise in user.scheduled_exercises(scheduled_day=current_day):
        new_exercise_for_today = ExerciseForToday(scheduled_exercise_id = scheduled_exercise.id)
        db.session.add(new_exercise_for_today)

    db.session.commit()