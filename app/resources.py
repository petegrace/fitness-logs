from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity

class AnnualStats(Resource):
    @jwt_required
    def get(self):
        return {
            "heading": "Your 2019 Stats",
            "counters": [{
                "category_name": "Run",
                "category_key": "cat_blue",
                "value": 51,
                "uom": "km"
            }, {
                "category_name": "Strength",
                "category_key": "cat_green",
                "value": 52,
                "uom": "sets"
            }, {
                "category_name": "Stretch",
                "category_key": "cat_green_outline",
                "value": 9,
                "uom": "sets"
            }, {
                "category_name": "Balance",
                "category_key": "cat_red",
                "value": 35,
                "uom": "sets"
            }]
        }