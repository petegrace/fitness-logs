from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, HiddenField, BooleanField, TextAreaField
from wtforms.validators import DataRequired

class CreateBlogPostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired()])
    content = TextAreaField("Content", validators=[DataRequired()], render_kw={"rows": 20})
    content_preview = TextAreaField("Content Preview", validators=[DataRequired()], render_kw={"rows": 6})
    publish = BooleanField("Publish?")
    submit = SubmitField("Create Post")