from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app import db
from app.models import User, ScheduledActivity
from app.ga import track_event

class AnnualStats(Resource):
    @jwt_required
    def get(self):
        email = get_jwt_identity()
        current_user = User.query.filter_by(email=email).first()

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

class PlannedActivities(Resource):
    def planned_activity_json(self, planned_activity):
        return {
            "id": planned_activity.id,
            "activity_type": planned_activity.activity_type,
			"scheduled_day": planned_activity.scheduled_day,
			"description": planned_activity.description,
			"planned_distance": planned_activity.planned_distance,
			"category_key": planned_activity.category_key
        }

    @jwt_required
    def get(self):
        user_id = get_jwt_identity()
        current_user = User.query.get(int(user_id))

        parser = reqparse.RequestParser()
        parser.add_argument("startDate", help="Start date for the (currently 1-day) period that we're returning planned activities for", required=True)
        args = parser.parse_args()
        
        start_date = datetime.strptime(args["startDate"], "%Y-%m-%d")
        day_of_week = start_date.strftime("%a")

        planned_activities = [self.planned_activity_json(activity) for activity in current_user.scheduled_activities_filtered(day_of_week).all()]

        return {
            "planned_activities": planned_activities
        }

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

        if len(data["description"]) == 0:
            data["description"] = None

        if len(data["planned_distance"]) == 0:
            data["planned_distance"] = None
            
        scheduled_activity = ScheduledActivity.query.get(int(planned_activity_id))
        scheduled_activity.description = data["description"] if data["description"] != "" else None
        scheduled_activity.planned_distance = data["planned_distance"] if ["planned_distance"] != "" else None
        db.session.commit()

        return "", 204