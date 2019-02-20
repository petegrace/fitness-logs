from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.models import User

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
        email = get_jwt_identity()
        current_user = User.query.filter_by(email=email).first()

        parser = reqparse.RequestParser()
        parser.add_argument("startDate", help="Start date for the (currently 1-day) period that we're returning planned activities for", required=True)
        args = parser.parse_args()
        
        start_date = datetime.strptime(args["startDate"], "%Y-%m-%d")
        day_of_week = start_date.strftime("%a")

        planned_activities = [self.planned_activity_json(activity) for activity in current_user.scheduled_activities_filtered(day_of_week).all()]

        return {
            "planned_activities": planned_activities
        }
