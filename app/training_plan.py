import calendar
from datetime import date
from app import app, db
from app.models import User, ExerciseForToday, ActivityForToday

# Should only call this function in scenarios where we are happy to clear out today's plan:
#   1) Logging in and the current date is different to last login date
#   2) Refreshed home page and the current date is different to last login date (should also update last login date)
def refresh_plan_for_today(user):
    current_day = calendar.day_abbr[date.today().weekday()]

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