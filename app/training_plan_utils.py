import calendar
from datetime import date, datetime, timedelta
from sqlalchemy import desc, and_, or_, null, func, distinct

from app import app, db
from app.models import User, ExerciseForToday, ActivityForToday, TrainingPlanTemplate, Activity, ExerciseCategory, ExerciseType, ScheduledExercise

# Should only call this function in scenarios where we are happy to clear out today's plan:
#   1) Logging in and the current date is different to last login date
#   2) Refreshed home page and the current date is different to last login date (should also update last login date)
def refresh_plan_for_today(user):
    current_date = date.today()

    # Clear out the activities for today and reload
    for activity_for_today in user.activities_for_today():
        db.session.delete(activity_for_today)

    for scheduled_activity in user.planned_activities_filtered(startDate=current_date, endDate=current_date):
        new_activity_for_today = ActivityForToday(scheduled_activity_id = scheduled_activity.id)
        db.session.add(new_activity_for_today)

    # Clear out the exercises for today and reload
    for exercise_for_today in user.exercises_for_today():
        db.session.delete(exercise_for_today)

    for scheduled_exercise in user.planned_exercises_filtered(startDate=current_date, endDate=current_date):
        new_exercise_for_today = ExerciseForToday(scheduled_exercise_id = scheduled_exercise.id)
        db.session.add(new_exercise_for_today)

    db.session.commit()

def add_to_plan_for_today(user, day):
    existing_exercises_for_today = user.exercises_for_today().all()
    existing_scheduled_exercise_ids = [exercise_for_today.scheduled_exercise_id for exercise_for_today in existing_exercises_for_today]
    existing_activities_for_today = user.activities_for_today().all()
    existing_scheduled_activity_ids = [activity_for_today.scheduled_activity_id for activity_for_today in existing_activities_for_today]    
    for scheduled_exercise in user.scheduled_exercises(scheduled_day=day):
    	if scheduled_exercise.id not in existing_scheduled_exercise_ids:
    		new_exercise_for_today = ExerciseForToday(scheduled_exercise_id = scheduled_exercise.id)
    		db.session.add(new_exercise_for_today)
    for scheduled_activity in user.scheduled_activities_filtered(scheduled_day=day):
    	if scheduled_activity.id not in existing_scheduled_activity_ids:
    		new_activity_for_today = ActivityForToday(scheduled_activity_id = scheduled_activity.id)
    		db.session.add(new_activity_for_today)
    db.session.commit()

def get_training_plan_generator_inputs(user, target_distance_m, target_race_date):
    timedelta_to_target_race = target_race_date - datetime.today()
    weeks_to_target_race = int(timedelta_to_target_race.days / 7)

    last_4_weeks_inputs = db.session.query(
                                    func.max(Activity.distance).label("longest_distance"),
                                    func.count(distinct(Activity.start_datetime.cast(db.Date))).label("runs_completed")
                                ).filter(Activity.owner == user
                                ).filter(Activity.activity_type == "Run"
                                ).filter(Activity.start_datetime >= datetime.today() - timedelta(days=28)
                                ).first()

    all_time_runs = db.session.query(
                                func.count(Activity.id).label("total_runs_above_target_distance")
                                ).filter(Activity.owner == user
                                ).filter(Activity.activity_type == "Run"
                                ).filter(Activity.distance >= target_distance_m
                                ).first()

    current_pb = db.session.query(
                                Activity.id,
                                Activity.name,
                                Activity.start_datetime.cast(db.Date).label("activity_date"),
                                Activity.average_speed
                            ).filter(Activity.owner == user
                            ).filter(Activity.activity_type == "Run"
                            ).filter(Activity.distance >= target_distance_m
                            ).order_by(Activity.average_speed.desc()
                            ).first()

    pre_pb_long_runs = db.session.query(
                                    func.count(Activity.id).label("runs_above_90pct_distance_count"),
                                    func.max(Activity.distance).label("longest_distance"),
                                    (current_pb.activity_date - func.min(Activity.start_datetime).cast(db.Date)).label("first_long_run_days_until_race"),
                                    (current_pb.activity_date - func.max(Activity.start_datetime).cast(db.Date)).label("last_long_run_days_until_race")
                                ).filter(Activity.owner == user
                                ).filter(Activity.activity_type == "Run"
                                ).filter(Activity.start_datetime >= current_pb.activity_date - timedelta_to_target_race
                                ).filter(Activity.start_datetime < current_pb.activity_date
                                ).filter(Activity.distance >= (target_distance_m * 0.9)
                                ).first()

    return last_4_weeks_inputs, all_time_runs, current_pb, pre_pb_long_runs, weeks_to_target_race

def copy_training_plan_template(template_id, user):
    template = TrainingPlanTemplate.query.get(int(template_id))

    # Create the categories used by the template
    if user.unused_category_keys().count() < template.template_exercise_categories.count():
        return "not enough spare categories"	
    else:
        new_exercise_types_count = 0

        for template_category in template.template_exercise_categories.all():
            if template_category.category_name not in [category.category_name for category in user.exercise_categories.all()]:
                unused_category_key = user.unused_category_keys().first()
                new_category = ExerciseCategory(owner=user,
                                                category_key=unused_category_key.category_key,
                                                category_name=template_category.category_name,
                                                fill_color=unused_category_key.fill_color,
                                                line_color=unused_category_key.line_color)
                db.session.add(new_category)
            else:
                new_category = ExerciseCategory.query.filter_by(owner=user).filter_by(category_name=template_category.category_name).first()
            
            # Create the exercise types associated with that category
            for template_exercise_type in template_category.template_exercise_types.all():
                if template_exercise_type.name not in [exercise_type.name for exercise_type in user.exercise_types.all()]:
                    new_exercise_type = ExerciseType(name=template_exercise_type.name,
                                                        owner=user,
                                                        exercise_category_id=new_category.id,
                                                        measured_by=template_exercise_type.measured_by,
                                                        default_reps=template_exercise_type.default_reps,
                                                        default_seconds=template_exercise_type.default_seconds)

                    db.session.add(new_exercise_type)
                    new_exercise_types_count += 1
                else:
                    new_exercise_type = ExerciseType.query.filter_by(owner=user).filter_by(name=template_exercise_type.name).first()
                
                # Add the exercise to the schedule on the required days
                for template_scheduled_exercise in template_exercise_type.template_scheduled_exercises:
                    scheduled_exercise = ScheduledExercise.query.filter(ExerciseType.owner==user
                            ).filter_by(is_removed=False
                            ).filter_by(type=new_exercise_type
                            ).filter_by(scheduled_day=template_scheduled_exercise.scheduled_day
                            ).first()

                    if not scheduled_exercise:
                        scheduled_exercise = ScheduledExercise(type=new_exercise_type,
                                                                recurrence="weekly",
                                                                scheduled_day=template_scheduled_exercise.scheduled_day,
                                                                sets=template_exercise_type.default_sets,
                                                                reps=new_exercise_type.default_reps,
                                                                seconds=new_exercise_type.default_seconds)
                        db.session.add(scheduled_exercise)	

        if not user.is_training_plan_user:
            user.is_training_plan_user = True

        db.session.commit()
        return "success"