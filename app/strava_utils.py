from flask import session
from datetime import datetime, date, timedelta
from stravalib.client import Client

from app import db, analysis
from app.ga import track_event
from app.models import Activity, ExerciseCategory, CalendarDay

def import_strava_activity(access_token, current_user):

    strava_client = Client()
    strava_client.access_token = access_token

    # also set the session variable we use for the old school Flask app so user doesn't need to reauthenticate
    session["strava_access_token"] = access_token

    try:
        athlete = strava_client.get_athlete()
    except:
        return {
            "status": "fail",
            "message": "Error trying retrieve athlete from Strava"
        }

    # Update user's UOM preferences based on what they have set in Strava
    if athlete.measurement_preference == "feet":
        current_user.distance_uom_preference = "miles"
        current_user.elevation_uom_preference = "feet"
    elif athlete.measurement_preference == "meters":
        current_user.distance_uom_preference = "km"
        current_user.elevation_uom_preference = "m"
    db.session.commit()

    most_recent_strava_activity_datetime = current_user.most_recent_strava_activity_datetime()

    # Start from 2000 if no imported activities
    most_recent_strava_activity_datetime = datetime(2000,1,1) if most_recent_strava_activity_datetime is None else most_recent_strava_activity_datetime

    activities = strava_client.get_activities(after = most_recent_strava_activity_datetime)
    activities_list = list(activities)

    new_activity_count = 0

    current_date = date.today()
    current_day = CalendarDay.query.filter(CalendarDay.calendar_date==current_date).first()
    current_week_start_date = current_day.calendar_week_start_date

    for strava_activity in activities_list:
        # if the start_datetime is today or this week then check if there's a scheduled activity in today's or this week's plan
        scheduled_activity = None

        if strava_activity.start_date.date() == current_date:
            scheduled_activity = current_user.planned_activities_filtered(startDate=current_date,
                                                                          endDate=current_date,
                                                                          planningPeriod="day",
                                                                          activityType=strava_activity.type).first()

        if scheduled_activity is None and strava_activity.start_date.date() >= current_week_start_date:
            scheduled_activity = current_user.planned_activities_filtered(startDate=current_week_start_date,
                                                                          endDate=current_date,
                                                                          planningPeriod="week",
                                                                          activityType=strava_activity.type).first()  

        print("{name} paired with {id}".format(name=strava_activity.name, id=scheduled_activity.id))
        activity = Activity(external_source = "Strava",
                            external_id = strava_activity.id,
                            owner = current_user,
                            scheduled_activity_id = scheduled_activity.id if scheduled_activity else None,
                            name = strava_activity.name,
                            start_datetime = strava_activity.start_date,
                            activity_type = strava_activity.type,
                            is_race = True if strava_activity.workout_type == "1" else False,
                            distance = strava_activity.distance.num,
                            total_elevation_gain = strava_activity.total_elevation_gain.num,
                            elapsed_time =strava_activity.elapsed_time,
                            moving_time = strava_activity.moving_time,
                            average_speed = strava_activity.average_speed.num,
                            average_cadence = (strava_activity.average_cadence * 2) if (strava_activity.type == "Run" and strava_activity.average_cadence is not None) else strava_activity.average_cadence,
                            average_heartrate = strava_activity.average_heartrate,
                            description = (strava_activity.description[:1000] if strava_activity.description else None)) #limit to first 1000 characters just in case

        db.session.add(activity)
        new_activity_count += 1

        if strava_activity.start_date.replace(tzinfo=None) > datetime.now() - timedelta(days=7):
            result = analysis.parse_streams(activity=activity)

    db.session.commit()

    return {
            "status": "success",
            "message": "Added {count} new activities from Strava!".format(count=new_activity_count)
    }