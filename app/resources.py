from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta, date
from sqlalchemy import desc, and_, or_, null, func, distinct
import logging

from app import db, utils, analysis
from app.models import  User, ExerciseCategory, ExerciseType, TrainingPlanTemplate
from app.models import ScheduledActivity, ScheduledActivitySkippedDate, ScheduledRace, ScheduledExercise, ScheduledExerciseSkippedDate, Activity, Exercise, CalendarDay
from app.ga import track_event
from app.strava_utils import import_strava_activity
from app.training_plan_utils import get_training_plan_generator_inputs, copy_training_plan_template, refresh_plan_for_today

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
        "planning_period": planned_activity.planning_period,
        "recurrence": planned_activity.recurrence,
        "planned_date": planned_activity.planned_date.strftime("%Y-%m-%d"),
        "activity_type": planned_activity.activity_type,
        "scheduled_day": planned_activity.scheduled_day,
        "description": planned_activity.description,
        "planned_distance": utils.format_distance_for_uom_preference(planned_activity.planned_distance, user, decimal_places=2, show_uom_suffix=False) if planned_activity.planned_distance else None,
        "planned_distance_formatted": utils.format_distance_for_uom_preference(planned_activity.planned_distance, user, decimal_places=2) if planned_activity.planned_distance else None,
        "category_key": planned_activity.category_key
    }

def combined_activity_json(combined_activity, user):
    return {
        "id": combined_activity.id,
		"source": combined_activity.source,
		"activity_datetime": combined_activity.activity_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
		"activity_date": combined_activity.activity_date.strftime("%Y-%m-%d"),
		"name": combined_activity.name,
		"scheduled_exercise_id": combined_activity.scheduled_exercise_id,
		"is_race": combined_activity.is_race,
		"reps": combined_activity.reps,
		"seconds": combined_activity.seconds,
        "distance": utils.format_distance_for_uom_preference(combined_activity.distance, user, show_uom_suffix=False) if combined_activity.distance else None,
        "distance_formatted": utils.format_distance_for_uom_preference(combined_activity.distance, user) if combined_activity.distance else None,
		"measured_by": combined_activity.measured_by,
		"external_id": combined_activity.external_id,
        "strava_url": "https://www.strava.com/activities/{strava_id}".format(strava_id = combined_activity.external_id) if combined_activity.source == "Strava" else None
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
        parser.add_argument("startDate", help="Start date for the period that we're returning completed activities for")
        parser.add_argument("endDate", help="Optional end date for the period that we're returning completed activities for. If left blank it will be the same as the start date")
        parser.add_argument("pageNo", help="Page number for when paging through recent activities in descending order")
        parser.add_argument("pageSize", help="Number of activities to return for the repquested page")
        parser.add_argument("combineExercises", help="When true, exercises will be unioned into the results with activities")
        args = parser.parse_args()
        
        if args["startDate"]:
            start_date = datetime.strptime(args["startDate"], "%Y-%m-%d")
            end_date = datetime.strptime(args["endDate"], "%Y-%m-%d") if args["endDate"] else start_date

            completed_activities = [completed_activity_json(activity, current_user) for activity in current_user.completed_activities_filtered(start_date, end_date).all()]

            result = {
                "completed_activities": completed_activities,
                "completed_exercises": completed_exercises_json(current_user, start_date, end_date)
            }
        elif args["pageNo"]:
            page_no = int(args["pageNo"])
            page_size = int(args["pageSize"]) if args["pageSize"] else app.config["EXERCISES_PER_PAGE"]
            combine_exercises = True if args["combineExercises"] == "true" else False

            if combine_exercises:
                recent_activities = current_user.recent_activities().order_by(desc("created_datetime"), desc("activity_datetime")).paginate(page_no, page_size, False) # Pagination object
                next_page_no = recent_activities.next_num if recent_activities.has_next else None
                prev_page_no = recent_activities.prev_num if recent_activities.has_prev else None
                recent_activities_json = [combined_activity_json(recent_activity, current_user) for recent_activity in recent_activities.items]
            else:
                recent_activities_json = [] # Not yet implemented

            result = {
                "page_no": page_no,
                "prev_page_no": prev_page_no,
                "next_page_no": next_page_no,
                "activities_and_exercises": recent_activities_json
            }

        return result, 200

    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("strava_access_token", help="Access token returned by Strava after the user has been through OAth2 authentication")
        data = parser.parse_args()

        track_event(category="Strava", action="Starting import of Strava activity", userId = str(current_user.id))
        result = import_strava_activity(data["strava_access_token"], current_user)

        response_messages = []

        if result["status"] == "success":
            track_event(category="Strava", action="Completed import of Strava activity", userId = str(current_user.id))
            response_messages.append(result["message"])
        else:
            track_event(category="Strava", action="Failure on import of Strava activity", userId = str(current_user.id))
            return "", 500

        # Evaluate the user's goals for the week based on new data
        analysis.evaluate_all_running_goals_for_current_week(current_user)
        
        #TODO: This duplicates what's in the routes version
        # If the user hasn't used categories yet then apply some defaults
        if len(current_user.exercise_categories.all()) == 0:
            run_category = ExerciseCategory(owner=current_user,
                                            category_key="cat_green",
                                            category_name="Run",
                                            fill_color="#588157",
                                            line_color="#588157")
            ride_category = ExerciseCategory(owner=current_user,
                                            category_key="cat_blue",
                                            category_name="Ride",
                                            fill_color="#3f7eba",
                                            line_color="#3f7eba")
            swim_category = ExerciseCategory(owner=current_user,
                                            category_key="cat_red",
                                            category_name="Swim",
                                            fill_color="#ef6461",
                                            line_color="#ef6461")
            db.session.add(run_category)
            db.session.add(ride_category)
            db.session.add(swim_category)
            db.session.commit()
            response_messages.append("Default categories have been added to colour-code your Strava activities. Configure them from the Manage Exercises section.")

        return {
            "messages": response_messages
        }, 200


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
            "planned_races": planned_races_json(current_user, start_date)
        }

    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("activity_type", help="Whether the activity is a Run, Ride or Swim")
        parser.add_argument("planned_date", help="Date that the activity is planned for")
        parser.add_argument("planning_period", help="Whether the activity is planned for a specific day or any time during the week (in which case planned_date should be the Monday of that week)")
        parser.add_argument("recurrence", help="Whether or not the planned activity will be repeated each week")
        parser.add_argument("description", help="More detail about the planned activity")
        parser.add_argument("planned_distance", help="Planned distance for the activity in the user's preferred UOM")
        parser.add_argument("target_race_distance", help="Distance of the planned race that a training plan is being generated for")
        parser.add_argument("target_race_date", help="Date of the planned race that a training plan is being generated for")
        parser.add_argument("long_run_planning_period", help="Specified by user when using training plan generator for how to plan the long run each week")
        parser.add_argument("long_run_day", help="Specifed by user when using the training plan generator and if planning period is day")
        data = parser.parse_args()

        if (data["activity_type"]):
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
                                                planning_period=data["planning_period"],
                                                recurrence=data["recurrence"],
                                                scheduled_date=planned_date,
                                                scheduled_day=planned_day_of_week,
                                                description=data["description"],
                                                planned_distance=planned_distance_m)
            db.session.add(scheduled_activity)
            db.session.commit()

            if (planned_date and planned_date.date() == date.today()) or (data["recurrence"] == "weekly" and planned_day_of_week == date.today().strftime("%a")):
                refresh_plan_for_today(current_user)

            message = "Added new planned activity"

        # Separate path to follow if the training plan generator is being used and we've got to generate a few activities
        elif (data["target_race_distance"]):
            target_race_date = datetime.strptime(data["target_race_date"], "%Y-%m-%d")
            target_distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["target_race_distance"]), current_user) if data["target_race_distance"] else None

            last_4_weeks_inputs, all_time_runs, current_pb, pre_pb_long_runs, weeks_to_target_race = get_training_plan_generator_inputs(current_user, target_distance_m, target_race_date)
        
            if (data["long_run_planning_period"] == "week"):
                first_long_run_date = db.session.query(CalendarDay.calendar_week_start_date
                                            ).filter(CalendarDay.calendar_date == datetime.today()
                                            ).first().calendar_week_start_date
            elif (data["long_run_planning_period"] == "day"):
                first_long_run_date = db.session.query(CalendarDay.calendar_date
                                            ).filter(CalendarDay.calendar_date >= datetime.today()
                                            ).filter(CalendarDay.day_of_week == data["long_run_day"]
                                            ).order_by(CalendarDay.calendar_date).first().calendar_date

            planned_races_during_training_period = db.session.query(ScheduledRace.scheduled_date,
                                                                    CalendarDay.calendar_week_start_date
                                                        ).join(CalendarDay, ScheduledRace.scheduled_date == CalendarDay.calendar_date
                                                        ).filter(ScheduledRace.owner == current_user
                                                        ).filter(ScheduledRace.scheduled_date >= datetime.today()
                                                        ).filter(ScheduledRace.scheduled_date < target_race_date
                                                        ).all()

            distance_to_add = target_distance_m - float(last_4_weeks_inputs.longest_distance)
            pct_to_add = (distance_to_add / last_4_weeks_inputs.longest_distance) if distance_to_add > 0 else 0

            if (all_time_runs.total_runs_above_target_distance > 0):
                # Aim to hit the target distance 2 weeks before
                weeks_to_add_distance = weeks_to_target_race - 1 - len(planned_races_during_training_period)
            #else:
                # Hit distance 1 week out where the distance is being eased back anyway
                weeks_to_add_distance = weeks_to_target_race - len(planned_races_during_training_period)
            
            min_distance_to_add_each_week = distance_to_add / weeks_to_add_distance

            # Now countdown through the weeks to go and add a long run (if the race is at least 10k)
            if target_distance_m > 10000:
                this_week_date = first_long_run_date
                this_week_distance = float(last_4_weeks_inputs.longest_distance)
                runs_at_target_distance = 0
                long_runs_added = 0

                while weeks_to_target_race > 0:
                    races_this_week = [race for race in planned_races_during_training_period if ((this_week_date - race.calendar_week_start_date).days >= 0 and (this_week_date - race.calendar_week_start_date).days < 7)]
                    
                    # Only add a long run if no race this week
                    if len(races_this_week) == 0:
                        this_week_distance = (this_week_distance * 1.1) if (this_week_distance * 1.1) > (this_week_distance + min_distance_to_add_each_week) else (this_week_distance + min_distance_to_add_each_week)
                        description = "Increasing long run distance towards the target race distance"

                        if this_week_distance >= target_distance_m:
                            this_week_distance = target_distance_m
                            description = "Get used to running the target race distance"

                            if runs_at_target_distance == 2 and pre_pb_long_runs.longest_distance > (target_distance_m * 1.05):
                                this_week_distance = target_distance_m * 1.1
                                description = "Try going a bit further than the target race distance, as in the lead up to {pb_race}".format(pb_race=current_pb.name)

                            runs_at_target_distance += 1

                        if weeks_to_target_race == 1:
                            this_week_distance = (target_distance_m * 0.8)
                            description = "Only 1 week to go so ease it back a little"

                        scheduled_activity = ScheduledActivity(activity_type="Run",
                                                    owner=current_user,
                                                    planning_period=data["long_run_planning_period"],
                                                    recurrence="once",
                                                    scheduled_date=this_week_date,
                                                    scheduled_day=None,
                                                    activity_subtype="Long Run",
                                                    description=description,
                                                    planned_distance=this_week_distance,
                                                    source="Training Plan Generator")

                        db.session.add(scheduled_activity)
                        long_runs_added += 1

                    weeks_to_target_race -= 1
                    this_week_date += timedelta(days=7)

            db.session.commit()
            track_event(category="Schedule", action="Added planned activities using Training Plan Generator", userId = str(user_id))
            message = "Added {long_run_count} long runs to training plan".format(long_run_count=long_runs_added)

        if current_user.is_training_plan_user == False:
            current_user.is_training_plan_user = True
            db.session.commit()            

        return {
            "message": message
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
        "entry_status": planned_race.entry_status,
        "race_website_url": planned_race.race_website_url,
        "notes": planned_race.notes,
        "distance": utils.format_distance_for_uom_preference(planned_race.distance, user, decimal_places=2, show_uom_suffix=False) if planned_race.distance else None,
        "distance_formatted": utils.format_distance_for_uom_preference(planned_race.distance, user, decimal_places=2) if planned_race.distance else None,
        "category_key": planned_race.category_key
    }

def planned_races_json(user, start_date):
    # For planned races we'll return everything in the next year as longer context is useful for training plan generator and possibly other stuff
    end_date = start_date + timedelta(days=365)
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
        parser.add_argument("distance", help="Race distance in the user's preferred UOM")
        parser.add_argument("entry_status", help="Whether the user has already Entered, or the race is a Probable or Possible")
        parser.add_argument("race_website_url", help="External web URL linking to the website for the race")
        parser.add_argument("notes", help="Any additional info about the race that the user wishes to record")
        data = parser.parse_args()

        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")

        if data["distance"] and len(data["distance"]) == 0:
            data["distance"] = None
            
        if data["entry_status"] and len(data["entry_status"]) == 0:
            data["entry_status"] = None

        if data["race_website_url"] and len(data["race_website_url"]) == 0:
            data["race_website_url"] = None

        if data["notes"] and len(data["notes"]) == 0:
            data["notes"] = None

        distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["distance"]), current_user) if data["distance"] else None

        track_event(category="Schedule", action="Scheduled race created", userId = str(current_user.id))
        scheduled_race = ScheduledRace(name=data["name"],
                                       race_type=data["race_type"],
                                       owner=current_user,
                                       scheduled_date=planned_date,
                                       distance=distance_m,
                                       entry_status=data["entry_status"],
                                       race_website_url=data["race_website_url"],
                                       notes=data["notes"])
        db.session.add(scheduled_race)
        db.session.commit()
        
        if current_user.is_training_plan_user == False:
            current_user.is_training_plan_user = True
            db.session.commit()

        return {
            "id": scheduled_race.id
        }, 201
        
        
class PlannedRace(Resource):
    @jwt_required
    def delete(self, planned_race_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled race removed", userId = str(user_id))
        
        scheduled_race = ScheduledRace.query.get(int(planned_race_id))

        if scheduled_race.user_id != user_id:
            return {
                "message": "race belongs to a different user"
            }, 403
            
        scheduled_race.is_removed = True
        db.session.commit()

        return "", 204

    @jwt_required
    def patch(self, planned_race_id):
        user_id = get_jwt_identity() 
        current_user = User.query.get(int(user_id))
        track_event(category="Schedule", action="Scheduled race updated", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("name", help="Name of the race")
        parser.add_argument("planned_date", help="Date that the activity is planned for")
        parser.add_argument("race_type", help="Whether the race is a Run, Ride, Swim or other type of event")
        parser.add_argument("distance", help="Race distance in the user's preferred UOM")
        parser.add_argument("entry_status", help="Whether the user has already Entered, or the race is a Probable or Possible")
        parser.add_argument("race_website_url", help="External web URL linking to the website for the race")
        parser.add_argument("notes", help="Any additional info about the race that the user wishes to record")
        data = parser.parse_args()

        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")

        if data["distance"] and len(data["distance"]) == 0:
            data["distance"] = None
            
        if data["entry_status"] and len(data["entry_status"]) == 0:
            data["entry_status"] = None

        if data["race_website_url"] and len(data["race_website_url"]) == 0:
            data["race_website_url"] = None

        if data["notes"] and len(data["notes"]) == 0:
            data["notes"] = None

        distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["distance"]), current_user) if data["distance"] else None

        scheduled_race = ScheduledRace.query.get(int(planned_race_id))
        if scheduled_race.user_id != user_id:
            return {
                "message": "race belongs to a different user"
            }, 403

        scheduled_race.name = data["name"]
        scheduled_race.scheduled_date = planned_date
        scheduled_race.race_type = data["race_type"]
        scheduled_race.distance = distance_m
        scheduled_race.entry_status = data["entry_status"]
        scheduled_race.race_website_url = data["race_website_url"]
        scheduled_race.notes = data["notes"]
        db.session.commit()

        return "", 204


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

    
class CompletedExercises(Resource):
    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("planned_exercise_id", help="Unique ID for planned exercise if the completed exercise was planned")
        parser.add_argument("exercise_type_id", help="Unique ID for exercise type being completed if it was an adhoc exercise")
        parser.add_argument("exercise_name", help="Name of the exercise when recording a new type")
        parser.add_argument("measured_by", help="Whether the exercise is measured by number of reps or time to hold position")
        parser.add_argument("exercise_category_id", help="Foreign key to category for exercise if creating a new type")
        parser.add_argument("reps", help="Number of reps completed if the exercise is measured in reps")
        parser.add_argument("seconds", help="Number of seconds the position was held for if the exercise is measured in seconds")        
        data = parser.parse_args()

        if data["planned_exercise_id"] and len(data["planned_exercise_id"]) == 0:
            data["planned_exercise_id"] = None

        if data["exercise_type_id"] and len(data["exercise_type_id"]) == 0:
            data["exercise_type_id"] = None

        if data["planned_exercise_id"]:
            track_event(category="Exercises", action="Exercise (scheduled) logged", userId = str(current_user.id))
            scheduled_exercise = ScheduledExercise.query.get(int(data["planned_exercise_id"]))
            
            completed_exercise = Exercise(type=scheduled_exercise.type,
                                    scheduled_exercise=scheduled_exercise,
                                    exercise_datetime=datetime.utcnow(),
                                    reps=scheduled_exercise.reps,
                                    seconds=scheduled_exercise.seconds)
        else:
            if not data["exercise_type_id"]:
                track_event(category="Exercises", action="New Exercise created for adhoc logging", userId = str(current_user.id))

                # Ensure that seconds and reps are none if the other is selected
                if data["measured_by"] == "reps":
                    data["seconds"] = None
                elif data["measured_by"] == "seconds":
                    data["reps"] = None

                exercise_type = ExerciseType(name=data["exercise_name"],
                                            owner=current_user,
                                            measured_by=data["measured_by"],
                                            default_reps=int(data["reps"]) if data["reps"] else None,
                                            default_seconds=int(data["seconds"]) if data["seconds"] else None,
                                            exercise_category_id=int(data["exercise_category_id"]) if data["exercise_category_id"] else None)
                db.session.add(exercise_type)
                db.session.commit()
                data["exercise_type_id"] = exercise_type.id
            
            # Now crack on with logging the exercise regardless of it existed before if it's just been created (and the id put into the dictionary element)
            track_event(category="Exercises", action="Exercise (adhoc) logged", userId = str(current_user.id))
            exercise_type = ExerciseType.query.get(int(data["exercise_type_id"]))
            
            completed_exercise = Exercise(type=exercise_type,
                                    exercise_datetime=datetime.utcnow(),
                                    reps=exercise_type.default_reps,
                                    seconds=exercise_type.default_seconds)

        db.session.add(completed_exercise)
        db.session.commit()
        return {
            "id": completed_exercise.id,
            "exercise_name": completed_exercise.type.name,
            "exercise_datetime": completed_exercise.exercise_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "measured_by": completed_exercise.type.measured_by,
            "reps": completed_exercise.reps,
            "seconds": completed_exercise.seconds
        }, 201

class CompletedExercise(Resource):
    @jwt_required
    def patch(self, completed_exercise_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled exercise updated", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("reps", help="Number of reps completed if the exercise is measured in reps")
        parser.add_argument("seconds", help="Number of seconds that the position was held for if the exercise is measured in seconds")
        data = parser.parse_args()
        
        if data["reps"] and len(data["reps"]) == 0:
            data["reps"] = None

        if data["seconds"] and len(data["seconds"]) == 0:
            data["seconds"] = None

        completed_exercise = Exercise.query.get(int(completed_exercise_id))
        
        if completed_exercise.type.user_id != user_id:
            return {
                "message": "exercise belongs to a different user"
            }, 403

        completed_exercise.reps = int(data["reps"]) if data["reps"] is not None else None
        completed_exercise.seconds = int(data["seconds"]) if data["seconds"] is not None else None
        db.session.commit()

        return {
            "id": completed_exercise.id,
            "exercise_name": completed_exercise.type.name,
            "exercise_datetime": completed_exercise.exercise_datetime.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "measured_by": completed_exercise.type.measured_by,
            "reps": completed_exercise.reps,
            "seconds": completed_exercise.seconds
        }, 200

    
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
        "completed_sets": planned_exercise.completed_sets,
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
            category_planned_exercises_for_day = [planned_exercise for planned_exercise in planned_exercises if planned_exercise.category_name==category.category_name and planned_exercise.planned_date==calendar_date.date() and planned_exercise.planning_period=="day"]
            if len(category_planned_exercises_for_day) > 0:
                planned_exercises_category = {
                    "planned_date": calendar_date.strftime("%Y-%m-%d"),
                    "planning_period": "day",
                    "category_name": category.category_name,
                    "category_key": category.category_key,
                    "exercises": [planned_exercise_json(planned_exercise) for planned_exercise in category_planned_exercises_for_day]
                }
                planned_exercises_by_category.append(planned_exercises_category)

            category_planned_exercises_for_week = [planned_exercise for planned_exercise in planned_exercises if planned_exercise.category_name==category.category_name and planned_exercise.planned_date==calendar_date.date() and planned_exercise.planning_period=="week"]
            if len(category_planned_exercises_for_week) > 0:
                planned_exercises_category = {
                    "planned_date": calendar_date.strftime("%Y-%m-%d"),
                    "planning_period": "week",
                    "category_name": category.category_name,
                    "category_key": category.category_key,
                    "exercises": [planned_exercise_json(planned_exercise) for planned_exercise in category_planned_exercises_for_week]
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
        parser.add_argument("planning_period", help="Whether the exercise is planned for a specific day or any time during the week (in which case planned_date should be the Monday of that week)")
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
            
            #  Check for same exercise already scheduled with weekly recurrence that we should update instead of create
            scheduled_exercise = ScheduledExercise.query.join(ExerciseType, (ExerciseType.id == ScheduledExercise.exercise_type_id)
                                                                        ).filter(ExerciseType.owner == current_user
                                                                        ).filter(ScheduledExercise.exercise_type_id==data["exercise_type_id"]
                                                                        ).filter(ScheduledExercise.planning_period==data["planning_period"]
                                                                        ).filter(ScheduledExercise.recurrence==data["recurrence"]
                                                                        ).filter(ScheduledExercise.scheduled_date==planned_date
                                                                        ).filter(ScheduledExercise.scheduled_day==planned_day_of_week
                                                                        ).first()

            if scheduled_exercise:
                scheduled_exercise.sets += 1
            else:
                # Schedule the exercise based on defaults
                track_event(category="Schedule", action="Exercise scheduled", userId = str(current_user.id))
                scheduled_exercise = ScheduledExercise(exercise_type_id=data["exercise_type_id"],
                                                    planning_period=data["planning_period"],
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
            skipped_date = datetime.strptime(scope, "%Y-%m-%d")
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

def last_4_weeks_inputs_json(query_results, user):
    return {
        "longest_distance": utils.format_distance_for_uom_preference(query_results.longest_distance, user, decimal_places=2, show_uom_suffix=False) if query_results.longest_distance else None,
        "longest_distance_formatted": utils.format_distance_for_uom_preference(query_results.longest_distance, user, decimal_places=2) if query_results.longest_distance else None,
        "runs_completed": query_results.runs_completed,
        "runs_per_week": round((float(query_results.runs_completed) / 4), 2)
    }

def current_pb_json(activity, user):
    return {
        "activity_name": activity.name,
        "average_pace_formatted": utils.format_pace_for_uom_preference(activity.average_speed, user),
        "activity_date": datetime.strftime(activity.activity_date, "%Y-%m-%d")
    }

def pre_pb_long_runs_json(query_results, user):
    return {
        "runs_above_90pct_distance_count": query_results.runs_above_90pct_distance_count,
        "longest_distance_formatted": utils.format_distance_for_uom_preference(query_results.longest_distance, user, decimal_places=2) if query_results.longest_distance else None,
        "weeks_between_first_long_run_and_pb": int(query_results.first_long_run_days_until_race / 7),
        "weeks_between_last_long_run_and_pb": int(query_results.last_long_run_days_until_race / 7)
    }


class TrainingPlanGenerator(Resource):
    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))
        track_event(category="Schedule", action="Selected race for Training Plan Generator", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("targetRaceDistance", help="Distance in meters that the race the user is targetting will be ran over")
        parser.add_argument("targetRaceDate", help="Date of the race that the training plan is for (YYYY-MM-DD)")
        data = parser.parse_args()

        target_race_date = datetime.strptime(data["targetRaceDate"], "%Y-%m-%d")
        target_distance_m = utils.convert_distance_to_m_for_uom_preference(float(data["targetRaceDistance"]), current_user) if data["targetRaceDistance"] else None

        last_4_weeks_inputs, all_time_runs, current_pb, pre_pb_long_runs, weeks_to_target_race = get_training_plan_generator_inputs(current_user, target_distance_m, target_race_date)

        # all-time runs >= distance

        # equivalent_period_before_pb
            # distance per week in 2 weeks before
            # distance per week n-2 weeks
            # runs per week


        return {
            "training_plan_generator_inputs": {
                "last_4_weeks": last_4_weeks_inputs_json(last_4_weeks_inputs, current_user),
                "total_runs_above_target_distance": all_time_runs.total_runs_above_target_distance,
                "current_pb": current_pb_json(current_pb, current_user),
                "weeks_to_target_race": weeks_to_target_race,
                "pre_pb_long_runs": pre_pb_long_runs_json(pre_pb_long_runs, current_user)
            } 
        }