# Fitness Logs

The place to set, track and smash your training goals.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing 
purposes. See deployment for notes on how to deploy the project on a live system.

### Pre-requisites

You'll need a local instance of Postgres set up.  Mac users can simply `brew install postgresql` - a decent guide to 
getting up and running with Postgres can be found 
[here](https://www.codementor.io/engineerapart/getting-started-with-postgresql-on-mac-osx-are8jcopb).

Once installed you can use the default user (e.g. via `psql postgres`) to create the required database, users 
and permissions, e.g.

```postgresql2html
CREATE DATABASE database_name;
CREATE USER my_username WITH PASSWORD 'my_password';
GRANT ALL PRIVILEGES ON DATABASE "database_name" to my_username;
```

### Running locally

Set up the project and virtual environments etc and `pip install -r requirements.txt` to install the relevant packages.
Rename `config_template.py` to `config.py` and update the values appropriate to your setup.  The config contains a
bunch of stuff related to deployment on [GCP](https://cloud.google.com/), which is not needed for getting up and
running locally.

TODO - `app.yaml`

## Deployment

TODO

## Built With

* [Flask](http://flask.pocoo.org/)
* [Strava](https://developers.strava.com/)