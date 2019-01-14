from app import app
from requests_oauth2.services import GoogleClient

def configured_google_client():
	google_auth = GoogleClient(
		client_id = app.config["GOOGLE_OAUTH2_CLIENT_ID"],
		client_secret=app.config["GOOGLE_OAUTH2_CLIENT_SECRET"],
		redirect_uri=app.config["GOOGLE_OAUTH2_REDIRECT_URI"],
	)
	return google_auth