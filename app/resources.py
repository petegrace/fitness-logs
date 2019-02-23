from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import desc, and_, or_, null
from app import db, utils
from app.models import User, ScheduledActivity, ExerciseCategory
from app.ga import track_event

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
                "value": str(activity_type_stat.total_distance),
                "uom": "km"
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

        return {
            "activity_types": activity_types
        }


class PlannedActivities(Resource):
    def planned_activity_json(self, planned_activity):
        return {
            "id": planned_activity.id,
            "planned_date": planned_activity.planned_date.strftime("%Y-%m-%d"),
			"activity_type": planned_activity.activity_type,
			"scheduled_day": planned_activity.scheduled_day,
			"description": planned_activity.description,
			"planned_distance": utils.convert_m_to_km(planned_activity.planned_distance) if planned_activity.planned_distance is not None else None,
			"category_key": planned_activity.category_key
        }

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

        planned_activities = [self.planned_activity_json(activity) for activity in current_user.planned_activities_filtered(start_date, end_date).all()]

        return {
            "planned_activities": planned_activities
        }

    @jwt_required
    def post(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("activity_type", help="Whether the activity is a Run, Ride or Swim")
        parser.add_argument("planned_date", help="Date that the activity is planned for")
        parser.add_argument("description", help="More detail about the planned activity")
        parser.add_argument("planned_distance", help="Planned distance for the activity in km")
        data = parser.parse_args()

        planned_date = datetime.strptime(data["planned_date"], "%Y-%m-%d")
        planned_day_of_week = planned_date.strftime("%a")

        if data["description"] and len(data["description"]) == 0:
            data["description"] = None

        if data["planned_distance"] and len(data["planned_distance"]) == 0:
            data["planned_distance"] = None

        track_event(category="Schedule", action="Scheduled activity created", userId = str(current_user.id))
        scheduled_activity = ScheduledActivity(activity_type=data["activity_type"],
                                               owner=current_user,
                                               scheduled_day=planned_day_of_week,
                                               description=data["description"],
                                               planned_distance=(int(data["planned_distance"])*1000) if data["planned_distance"] else None) #TODO make sure we're consistent on km vs m
        db.session.add(scheduled_activity)
        db.session.commit()

        return {
            "id": scheduled_activity.id
        }, 201


class PlannedActivity(Resource):
    @jwt_required
    def delete(self, planned_activity_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled activity removed", userId = str(user_id))

        scheduled_activity = ScheduledActivity.query.get(int(planned_activity_id))
        scheduled_activity.is_removed = True
        db.session.commit()

        return "", 204

    @jwt_required
    def patch(self, planned_activity_id):
        user_id = get_jwt_identity() 
        track_event(category="Schedule", action="Scheduled activity updated", userId = str(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("description", help="More detail about the planned activity")
        parser.add_argument("planned_distance", help="Planned distance for the activity in km")
        data = parser.parse_args()

        if data["description"] and len(data["description"]) == 0:
            data["description"] = None

        if data["planned_distance"] and len(data["planned_distance"]) == 0:
            data["planned_distance"] = None

        scheduled_activity = ScheduledActivity.query.get(int(planned_activity_id))
        scheduled_activity.description = data["description"] if data["description"] != "" else None
        scheduled_activity.planned_distance = (int(data["planned_distance"])*1000) if ["planned_distance"] != "" else None
        db.session.commit()

        return "", 204