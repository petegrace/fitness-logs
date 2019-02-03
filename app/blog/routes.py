from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_required
from app.blog import bp

@bp.route("/")
@login_required
def index():
	return render_template("blog/index.html", title="Blog")