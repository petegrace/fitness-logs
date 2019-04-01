from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta, date
from sqlalchemy import desc, and_, or_, null
import logging

from app import db, utils
from app.models import  User, ExerciseCategory, ExerciseType, TrainingPlanTemplate
from app.models import ScheduledActivity, ScheduledActivitySkippedDate, ScheduledRace, ScheduledExercise, ScheduledExerciseSkippedDate
from app.ga import track_event
from app.training_plan_utils import copy_training_plan_template, refresh_plan_for_today

class Monitoring(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("type", help="Type of message to be logged, e.g. error")
        parser.add_argument("message", help="Message to be logged")
        data = parser.parse_args()

        if data["type"] == "error":
            logging.error(data["message"])
        else:
            logging.info(data["message"])

        return "", 204

class AnnualStats(Resource):
    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        counters = []
        for activity_type_stat in current_user.current_year_activity_stats().all():
            counters.append({
                "category_name": activity_type_stat.activity_type,
                "category_key": activity_type_stat.category_key,
                "value": str(utils.format_distance_for_uom_preference(m=activity_type_stat.total_distance, user=current_user, decimal_places=0, show_uom_suffix=False)),
                "uom": current_user.distance_uom_preference if current_user.distance_uom_preference else "km"
            })
        
        for exercise_category_stat in current_user.current_year_exercise_stats().all():
            counters.append({
                "category_name": exercise_category_stat.category_name,
                "category_key": exercise_category_stat.category_key,
                "value": str(exercise_category_stat.total_sets),
                "uom": "sets"
            })

        return {
            "heading": "Your 2019 Stats",
            "counters": counters
        }

class ActivityTypes(Resource):
    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        activity_types = []
        for activity_type in current_user.exercise_categories.filter(ExerciseCategory.category_name.in_(["Run", "Ride", "Swim"])).all():
            activity_types.append({
                "activity_type": activity_type.category_name,
                "category_key": activity_type.category_key
            })

        exercise_types = exercise_types_json(current_user)
        exercise_categories = exercise_categories_json(current_user)

        return {
            "activity_types": activity_types,
            "exercise_types": exercise_types,
            "exercise_categories": exercise_categories
        }

def exercise_types_json(user):
    exercise_types = []
    for exercise_type in user.exercise_types_ordered().all():
        exercise_types.append({
            "id": exercise_type.id,
			"exercise_name": exercise_type.name,
			"category_key": exercise_type.category_key,
			"category_name": exercise_type.category_name,
			"measured_by": exercise_type.measured_by,
			"default_reps": exercise_type.default_reps,
			"default_seconds": exercise_type.default_seconds
        })

    return exercise_types

def exercise_categories_json(user):
    exercise_categories = []
    for exercise_category in user.exercise_categories.filter(ExerciseCategory.category_name.notin_(["Run", "Ride", "Swim"])).all():
        exercise_categories.append({
            "id": exercise_category.id,
			"category_name": exercise_category.category_name,
			"category_key": exercise_category.category_key
        })

    return exercise_categories

def training_plan_template_json(template):
    return {
        "id": template.id,
	    "name": template.name,
	    "description": template.description,
	    "link_url": template.link_url,
	    "link_text": template.link_text
    }

class TrainingPlanTemplates(Resource):
    # Needn't be authenticated for this one
    def get(self):
        templates = [training_plan_template_json(template) for template in TrainingPlanTemplate.query.all()]

        return {
            "training_plan_templates": templates
        }
    
def planned_activity_json(planned_activity, user):
    return {
        "id": planned_activity.id,
        "recurrence": planned_activity.recurrence,
        "planned_date": planned_activity.planned_date.strftime("%Y-%m-%d"),
        "activity_type": planned_activity.activity_type,
        "scheduled_day": planned_activity.scheduled_day,
        "description": planned_activity.description,
        "planned_distance": utils.format_distance_for_uom_preference(planned_activity.planned_distance, user, decimal_places=2, show_uom_suffix=False) if planned_activity.planned_distance else None,
        "category_key": planned_activity.category_key
    }

def completed_activity_json(completed_activity, user):
    average_climbing_gradient = round((completed_activity.total_elevation_gain / completed_activity.distance) * 100, 1) if completed_activity.distance > 0 and completed_activity.total_elevation_gain else 0
    average_climbing_gradient_formatted = str(average_climbing_gradient) + " %" if average_climbing_gradient else None

    return {
        "id": completed_activity.id,
        "name": completed_activity.name,
        "activity_date": completed_activity.activity_date.strftime("%Y-%m-%d"),
        "activity_type": completed_activity.activity_type,
        "distance": utils.format_distance_for_uom_preference(completed_activity.distance, user, show_uom_suffix=False),
        "distance_formatted": utils.format_distance_for_uom_preference(completed_activity.distance, user),
        "moving_time": str(completed_activity.moving_time), 
        "average_pace_formatted": utils.format_pace_for_uom_preference(completed_activity.average_speed, user),
        "average_cadence": str(completed_activity.average_cadence),
        "median_cadence": str(completed_activity.median_cadence),
        "average_heartrate": str(completed_activity.average_heartrate),
        "total_elevation_gain_formatted": "Bad Data" if completed_activity.is_bad_elevation_data else (utils.format_elevation_for_uom_preference(completed_activity.total_elevation_gain, user) if completed_activity.total_elevation_gain else None),
        "average_climbing_gradient_formatted": "Bad Data" if completed_activity.is_bad_elevation_data else average_climbing_gradient_formatted,
        "description": completed_activity.description,
        "is_race": completed_activity.is_race,
        "category_key": completed_activity.category_key,
        "strava_url": "https://www.strava.com/activities/{strava_id}".format(strava_id = completed_activity.external_id)
    }


class CompletedActivities(Resource):

    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("startDate", help="Start date for the period that we're returning completed activities for", required=True)
        parser.add_argument("endDate", help="Optional end date for the period that we're returning completed activities for. If left blank it will be the same as the start date")
        args = parser.parse_args()
        
        start_date = datetime.strptime(args["startDate"], "%Y-%m-%d")
        end_date = datetime.strptime(args["endDate"], "%Y-%m-%d") if args["endDate"] else start_date

        completed_activities = [completed_activity_json(activity, current_user) for activity in current_user.completed_activities_filtered(start_date, end_date).all()]

        return {
            "completed_activities": completed_activities,
            "completed_exercises": completed_exercises_json(current_user, start_date, end_date)
        }


class PlannedActivities(Resource):

    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("startDate", help="Start date for the period that we're returning planned activities for", required=True)
        parser.add_argument("endDate", help="Optional end date for the period that we're returning planned activities for. If left blank it will be the same as the start date")
        args = parser.parse_args()
        
        start_date = datetime.strptime(args["startDate"], "%Y-%m-%d")
        end_date = datetime.strptime(args["endDate"], "%Y-%m-%d") if args["endDate"] else start_date

        planned_activities = [planned_activity_json(activity, current_user) for activity in current_user.planned_activities_filtered(start_date, end_date).all()]

        return {
            "planned_activities": planned_activities,
            "planned_exercises": planned_exercises_json(current_user, start_date, end_date),
            "planned_races": planned_races_json(current_user, start_date, end_date)
        }

    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("activity_type", help="Whether the activity is a Run, Ride or Swim")
        parser.add_argument("planned_date", help="Date that the activity is planned for")
        parser.add_argument("recurrence", help="Whether or not the planned activity will be repeated each week")
        parser.add_argument("description", help="More detail about the planned activity")
        parser.add_argument("planned_distance", help="Planned distance for the activity in the user's preferred UOM")
        data = parser.parse_args()

        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")
        planned_day_of_week = planned_date.strftime("%a") if data["recurrence"] == "weekly" else None
        planned_date = planned_date if data["recurrence"] == "once" else None

        if data["description"] and len(data["description"]) == 0:
            data["description"] = None

        if data["planned_distance"] and len(data["planned_distance"]) == 0:
            data["planned_distance"] = None

        planned_distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["planned_distance"]), current_user) if data["planned_distance"] else None

        track_event(category="Schedule", action="Scheduled activity created", userId = str(current_user.id))
        scheduled_activity = ScheduledActivity(activity_type=data["activity_type"],
                                               owner=current_user,
                                               recurrence=data["recurrence"],
                                               scheduled_date=planned_date,
                                               scheduled_day=planned_day_of_week,
                                               description=data["description"],
                                               planned_distance=planned_distance_m)
        db.session.add(scheduled_activity)
        db.session.commit()

        if (planned_date and planned_date.date() == date.today()) or (data["recurrence"] == "weekly" and planned_day_of_week == date.today().strftime("%a")):
            refresh_plan_for_today(current_user)
        
        if current_user.is_training_plan_user == False:
            current_user.is_training_plan_user = True
            db.session.commit()
            

        return {
            "id": 1#scheduled_activity.id
        }, 201


class PlannedActivity(Resource):
    @jwt_required
    def delete(self, planned_activity_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled activity removed", userId = str(user_id))
        
        parser = reqparse.RequestParser()
        parser.add_argument("scope", help="Either 'all' to remove the activity from the plan completely or a date to add to skipped dates table")
        args = parser.parse_args()
        scope = args["scope"] if args["scope"] else "all"
        scheduled_activity = ScheduledActivity.query.get(int(planned_activity_id))

        if scheduled_activity.user_id != user_id:
            return {
                "message": "activity belongs to a different user"
            }, 403
            
        if scope == "all":
            scheduled_activity.is_removed = True
            db.session.commit()
        else:
            skipped_date = datetime.strptime(scope, "%Y-%m-%d")
            scheduled_activity_skipped_date = ScheduledActivitySkippedDate(scheduled_activity=scheduled_activity,
                                                                           skipped_date=skipped_date)
            db.session.add(scheduled_activity_skipped_date)
            db.session.commit()

        # TODO: We can optimise this but needs a bit of extra querying to know what the date affected is, so for now just refresh every time
        current_user = User.query.get(int(user_id))
        refresh_plan_for_today(current_user)

        return "", 204

    @jwt_required
    def patch(self, planned_activity_id):
        user_id = get_jwt_identity() 
        current_user = User.query.get(int(user_id))
        track_event(category="Schedule", action="Scheduled activity updated", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("planned_date", help="Date that the activity is planned for")
        parser.add_argument("recurrence", help="Whether or not the planned activity will be repeated each week")
        parser.add_argument("description", help="More detail about the planned activity")
        parser.add_argument("planned_distance", help="Planned distance for the activity in km")
        data = parser.parse_args()

        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")
        planned_day_of_week = planned_date.strftime("%a") if data["recurrence"] == "weekly" else None
        planned_date = planned_date if data["recurrence"] == "once" else None

        if data["description"] and len(data["description"]) == 0:
            data["description"] = None

        if data["planned_distance"] and len(data["planned_distance"]) == 0:
            data["planned_distance"] = None

        planned_distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["planned_distance"]), current_user) if data["planned_distance"] else None

        scheduled_activity = ScheduledActivity.query.get(int(planned_activity_id))

        if scheduled_activity.user_id != user_id:
            return {
                "message": "activity belongs to a different user"
            }, 403

        scheduled_activity.recurrence = data["recurrence"]
        scheduled_activity.scheduled_date = planned_date
        scheduled_activity.scheduled_day = planned_day_of_week
        scheduled_activity.description = data["description"] if data["description"] != "" else None
        scheduled_activity.planned_distance = planned_distance_m
        db.session.commit()

        return "", 204


def planned_race_json(planned_race, user):
    return {
        "id": planned_race.id,
        "name": planned_race.name,
        "race_type": planned_race.race_type,
        "planned_date": planned_race.scheduled_date.strftime("%Y-%m-%d"),
        "notes": planned_race.notes,
        "distance": utils.format_distance_for_uom_preference(planned_race.distance, user, decimal_places=2, show_uom_suffix=False) if planned_race.distance else None,
        "category_key": planned_race.category_key
    }

def planned_races_json(user, start_date, end_date):
    planned_races = [planned_race_json(race, user) for race in user.planned_races_filtered(start_date, end_date).all()]
    return planned_races


class PlannedRaces(Resource):

    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("name", help="Name of the race")
        parser.add_argument("planned_date", help="Date that the activity is planned for")
        parser.add_argument("race_type", help="Whether the race is a Run, Ride, Swim or other type of event")
        parser.add_argument("notes", help="Any additional info about the race that the user wishes to record")
        parser.add_argument("distance", help="Race distance in the user's preferred UOM")
        data = parser.parse_args()

        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")

        if data["notes"] and len(data["notes"]) == 0:
            data["notes"] = None

        if data["distance"] and len(data["distance"]) == 0:
            data["distance"] = None

        distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["distance"]), current_user) if data["distance"] else None

        track_event(category="Schedule", action="Scheduled race created", userId = str(current_user.id))
        scheduled_race = ScheduledRace(name=data["name"],
                                       race_type=data["race_type"],
                                       owner=current_user,
                                       scheduled_date=planned_date,
                                       notes=data["notes"],
                                       distance=distance_m)
        db.session.add(scheduled_race)
        db.session.commit()
        
        if current_user.is_training_plan_user == False:
            current_user.is_training_plan_user = True
            db.session.commit()
            

        return {
            "id": 1#scheduled_activity.id
        }, 201


def completed_exercise_json(completed_exercise):
    return {
        "id": completed_exercise.id,
        "exercise_date": completed_exercise.exercise_date.strftime("%Y-%m-%d"),
        "exercise_time": completed_exercise.exercise_datetime.strftime("%H:%M:%S"),
        "exercise_type_id": completed_exercise.exercise_type_id,
        "exercise_name": completed_exercise.exercise_name,
        "category_name": completed_exercise.category_name,
        "measured_by": completed_exercise.measured_by,
        "reps": completed_exercise.reps,
        "seconds": completed_exercise.seconds,
        "category_key": completed_exercise.category_key
    }

def completed_exercises_json(user, start_date, end_date):
    completed_exercises = user.completed_exercises_filtered(start_date, end_date).all()
    categories = user.exercise_categories.all()

    # Make sure we still present any uncategorised exercises
    temp_uncategorised = ExerciseCategory(category_name="Uncategorised",
                                          category_key="uncategorised",
                                          owner=user)
    categories.append(temp_uncategorised)

    completed_exercises_by_category = []

    # Group up the planned exercises by category
    for category in categories:
        calendar_date = start_date
        
        while calendar_date <= end_date:
            category_completed_exercises = [completed_exercise for completed_exercise in completed_exercises if completed_exercise.category_name==category.category_name and completed_exercise.exercise_date==calendar_date.date()]
            if len(category_completed_exercises) > 0:
                completed_exercises_category = {
                    "exercise_date": calendar_date.strftime("%Y-%m-%d"),
                    "category_name": category.category_name,
                    "category_key": category.category_key,
                    "exercises": [completed_exercise_json(completed_exercise) for completed_exercise in category_completed_exercises]
                }
                completed_exercises_by_category.append(completed_exercises_category)

            calendar_date = calendar_date + timedelta(days=1)

    return completed_exercises_by_category

    
def planned_exercise_json(planned_exercise):
    return {
        "id": planned_exercise.id,
        "recurrence": planned_exercise.recurrence,
        "planned_date": planned_exercise.planned_date.strftime("%Y-%m-%d"),
        "exercise_type_id": planned_exercise.exercise_type_id,
        "exercise_name": planned_exercise.exercise_name,
        "category_name": planned_exercise.category_name,
        "scheduled_day": planned_exercise.scheduled_day,
        "planned_sets": planned_exercise.sets,
        "measured_by": planned_exercise.measured_by,
        "planned_reps": planned_exercise.reps,
        "planned_seconds": planned_exercise.seconds,
        "category_key": planned_exercise.category_key
    }

def planned_exercises_json(user, start_date, end_date):
    planned_exercises = user.planned_exercises_filtered(start_date, end_date).all()
    categories = user.exercise_categories.all()

    # Make sure we still present any uncategorised exercises
    temp_uncategorised = ExerciseCategory(category_name="Uncategorised",
                                          category_key="uncategorised",
                                          owner=user)
    categories.append(temp_uncategorised)

    planned_exercises_by_category = []

    # Group up the planned exercises by category
    for category in categories:
        calendar_date = start_date
        
        while calendar_date <= end_date:
            category_planned_exercises = [planned_exercise for planned_exercise in planned_exercises if planned_exercise.category_name==category.category_name and planned_exercise.planned_date==calendar_date.date()]
            if len(category_planned_exercises) > 0:
                planned_exercises_category = {
                    "planned_date": calendar_date.strftime("%Y-%m-%d"),
                    "category_name": category.category_name,
                    "category_key": category.category_key,
                    "exercises": [planned_exercise_json(planned_exercise) for planned_exercise in category_planned_exercises]
                }
                planned_exercises_by_category.append(planned_exercises_category)

            calendar_date = calendar_date + timedelta(days=1)

    return planned_exercises_by_category
        

class PlannedExercises(Resource):
    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("exercise_type_id", help="Foreign key for the type of exercise being scheduled")
        parser.add_argument("exercise_name", help="Name of the exercise when scheduling a new type")
        parser.add_argument("measured_by", help="Whether the exercise is measured by number of reps or time to hold position")
        parser.add_argument("exercise_category_id", help="Foreign key to category for exercise if creating a new type")
        parser.add_argument("recurrence", help="Whether or not the planned exercise will be repeated each week")
        parser.add_argument("planned_date", help="Date that the exercise is planned for")
        parser.add_argument("planned_reps", help="Planned number of reps to do in each set if the exercise is measured in reps")
        parser.add_argument("planned_seconds", help="Planned number of seconds to hold the position for in each set if the exercise is measured in seconds")
        # template id gets supplied on its own by a separate type of request to copy template into pllan
        parser.add_argument("template_id", help="Id for a template that the user wants to copy into their plan")
        data = parser.parse_args()

        if data["template_id"]:
            track_event(category="Schedule", action="Attempting to copy training plan from template", userId = str(current_user.id))
            result = copy_training_plan_template(template_id=data["template_id"], user=current_user)
            if result == "not enough spare categories":
                track_event(category="Schedule", action="Not enough spare exercise categories to copy template.", userId = str(current_user.id))
                return {
                    "message": result
                }, 409 # conflict status code
                
            track_event(category="Schedule", action="Completed copying training plan from template", userId = str(current_user.id))

            if current_user.is_training_plan_user == False:
                current_user.is_training_plan_user = True
                db.session.commit()
                
            response_body = {
                "message": result
            }
        else:
            planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")
            planned_day_of_week = planned_date.strftime("%a") if data["recurrence"] == "weekly" else None
            planned_date = planned_date if data["recurrence"] == "once" else None

            if data["planned_reps"] and len(data["planned_reps"]) == 0:
                data["planned_reps"] = None

            if data["planned_seconds"] and len(data["planned_seconds"]) == 0:
                data["planned_seconds"] = None

            if (not data["exercise_type_id"]):
                # TODO: we should move this into an exercise types function for reuse
                track_event(category="Exercises", action="New Exercise created for scheduling", userId = str(current_user.id))

                # Ensure that seconds and reps are none if the other is selected
                if data["measured_by"] == "reps":
                    data["planned_seconds"] = None
                elif data["measured_by"] == "seconds":
                    data["planned_reps"] = None

                exercise_type = ExerciseType(name=data["exercise_name"],
                                            owner=current_user,
                                            measured_by=data["measured_by"],
                                            default_reps=int(data["planned_reps"]) if data["planned_reps"] else None,
                                            default_seconds=int(data["planned_seconds"]) if data["planned_seconds"] else None,
                                            exercise_category_id=int(data["exercise_category_id"]) if data["exercise_category_id"] else None)
                
                db.session.add(exercise_type)
                db.session.commit()
                data["exercise_type_id"] = exercise_type.id
            
            # Schedule the exercise based on defaults
            track_event(category="Schedule", action="Exercise scheduled", userId = str(current_user.id))
            scheduled_exercise = ScheduledExercise(exercise_type_id=data["exercise_type_id"],
                                                recurrence=data["recurrence"],
                                                scheduled_date=planned_date,
                                                scheduled_day=planned_day_of_week,
                                                sets=1,
                                                reps=data["planned_reps"],
                                                seconds=data["planned_seconds"])
            db.session.add(scheduled_exercise)
            db.session.commit()

            if current_user.is_training_plan_user == False:
                current_user.is_training_plan_user = True
                db.session.commit()

            response_body = {
                "id": scheduled_exercise.id
            }

        # refresh today's plan at the end regardless rather than trying to work out all the permutations that might affect today
        refresh_plan_for_today(current_user)

        return response_body, 201
    
#     @jwt_required
#     def get(self):
#         user_id = get_jwt_identity()
#         current_user = User.query.get(int(user_id))
        
#         parser = reqparse.RequestParser()
#         parser.add_argument("startDate", help="Start date for the period that we're returning planned activities for", required=True)
#         parser.add_argument("endDate", help="Optional end date for the period that we're returning planned activities for. If left blank it will be the same as the start date")
#         args = parser.parse_args()
        
#         start_date = datetime.strptime(args["startDate"], "%Y-%m-%d")
#         end_date = datetime.strptime(args["endDate"], "%Y-%m-%d") if args["endDate"] else start_date

class PlannedExercise(Resource):
    @jwt_required
    def delete(self, planned_exercise_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled exercise removed", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("scope", help="Either 'all' to remove the exercise from the plan completely or a date to add to skipped dates table")
        args = parser.parse_args()
        scope = args["scope"] if args["scope"] else "all"

        scheduled_exercise = ScheduledExercise.query.get(int(planned_exercise_id))

        if scheduled_exercise.type.user_id != user_id:
            return {
                "message": "exercise belongs to a different user"
            }, 403

        if scope == "all":
            scheduled_exercise.is_removed = True
            db.session.commit()
        else:
            print(scope)
            skipped_date = datetime.strptime(scope, "%Y-%m-%d")
            print(skipped_date)
            scheduled_exercise_skipped_date = ScheduledExerciseSkippedDate(scheduled_exercise=scheduled_exercise,
                                                                           skipped_date=skipped_date)
            db.session.add(scheduled_exercise_skipped_date)
            db.session.commit()

        # refresh today's plan at the end regardless rather than trying to work out all the permutations that might affect today
        current_user = User.query.get(int(user_id))
        refresh_plan_for_today(current_user)

        return "", 204

    @jwt_required
    def patch(self, planned_exercise_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled exercise updated", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("planned_date", help="Date that the exercise is planned for")
        parser.add_argument("recurrence", help="Whether or not the planned exercise will be repeated each week")
        parser.add_argument("planned_sets", help="Planned number of sets to do on the given day")
        parser.add_argument("planned_reps", help="Planned number of reps to do in each set if the exercise is measured in reps")
        parser.add_argument("planned_seconds", help="Planned number of seconds to hold the position for in each set if the exercise is measured in seconds")
        data = parser.parse_args()
        
        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")
        planned_day_of_week = planned_date.strftime("%a") if data["recurrence"] == "weekly" else None
        planned_date = planned_date if data["recurrence"] == "once" else None

        if data["planned_sets"] and len(data["planned_sets"]) == 0:
            data["planned_sets"] = None

        if data["planned_reps"] and len(data["planned_reps"]) == 0:
            data["planned_reps"] = None

        if data["planned_seconds"] and len(data["planned_seconds"]) == 0:
            data["planned_seconds"] = None

        scheduled_exercise = ScheduledExercise.query.get(int(planned_exercise_id))
        
        if scheduled_exercise.type.user_id != user_id:
            return {
                "message": "exercise belongs to a different user"
            }, 403

        scheduled_exercise.recurrence = data["recurrence"]
        scheduled_exercise.scheduled_date = planned_date
        scheduled_exercise.scheduled_day = planned_day_of_week
        scheduled_exercise.sets = int(data["planned_sets"]) if data["planned_sets"] is not None else None
        scheduled_exercise.reps = int(data["planned_reps"]) if data["planned_reps"] is not None else None
        scheduled_exercise.seconds = int(data["planned_seconds"]) if data["planned_seconds"] is not None else None
        db.session.commit()

        return "", 204