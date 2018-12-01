import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or '<secret_key>'

    # GCP Stuff
    PROJECT_ID = '<gcp_project_id>'
    GOOGLE_OAUTH2_CLIENT_ID = '<gcp_oauth_client_id>'
    GOOGLE_OAUTH2_CLIENT_SECRET = '<gcp_oauth_secret>'

    # CloudSQL & SQLAlchemy configuration
    CLOUDSQL_USER = '<db_user>'
    CLOUDSQL_PASSWORD = '<db_password>'
    CLOUDSQL_DATABASE = '<db_name>'
    CLOUDSQL_CONNECTION_NAME = '<gcp_project_id>:<gcp_region>:<db_name>'

    LOCAL_SQLALCHEMY_DATABASE_URI = (
        'postgresql+psycopg2://{user}:{password}@127.0.0.1:5432/{database}').format(
            user=CLOUDSQL_USER, password=CLOUDSQL_PASSWORD,
            database=CLOUDSQL_DATABASE)

    LIVE_SQLALCHEMY_DATABASE_URI = (
        'postgresql+psycopg2://{user}:{password}@/{database}?host=/cloudsql/{connection_name}').format(
            user=CLOUDSQL_USER, password=CLOUDSQL_PASSWORD,
            database=CLOUDSQL_DATABASE, connection_name=CLOUDSQL_CONNECTION_NAME)

    if os.environ.get('GAE_INSTANCE'):
        SQLALCHEMY_DATABASE_URI = LIVE_SQLALCHEMY_DATABASE_URI
    else:
        SQLALCHEMY_DATABASE_URI = LOCAL_SQLALCHEMY_DATABASE_URI

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Strava auth
    STRAVA_OAUTH2_CLIENT_ID = '<strava_id_probs_int>'
    STRAVA_OAUTH2_CLIENT_SECRET = '<strava_oauth_secret>'

    if os.environ.get('GAE_INSTANCE'):
        STRAVA_OAUTH2_REDIRECT_URI = "https://fitness-logs.appspot.com/connect_strava/authorize"
    else:
        STRAVA_OAUTH2_REDIRECT_URI = "http://127.0.0.1:5000/connect_strava/authorize"

    # Google Analytics
    GA_TRACKING_ID = os.environ.get('GA_TRACKING_ID') or '<ga_id>'

    # Custom app settings
    EXERCISES_PER_PAGE = 5