from flask import render_template, flash, redirect, url_for, request, session
from flask_login import current_user, login_required
from app import db
from app.models import BlogPost
from app.blog import bp
from app.blog.forms import CreateBlogPostForm
import re

@bp.route("/")
@bp.route("/index")
def index():
    published_posts = BlogPost.query.filter_by(is_published=True).order_by(BlogPost.id.desc()).all()
    
    return render_template("blog/index.html", title="Blog", published_posts=published_posts)


@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    # Only let authorised blog authors create posts
    if not current_user.is_blog_author:
        return redirect(url_for("blog.index"))

    form = CreateBlogPostForm()

    # For a post
    if form.validate_on_submit():
        slug = re.sub("[^\w]+", "-", form.title.data.lower())
        new_post = BlogPost(author=current_user,
                            title=form.title.data,
                            slug=slug,
                            content=form.content.data,
                            content_preview=form.content_preview.data,
                            is_published=form.publish.data)

        db.session.add(new_post)
        db.session.commit()

        return redirect(url_for("blog.drafts"))

    return render_template("blog/create.html", title="Create Blog Post", form=form)


@bp.route("/<slug>")
def view_post(slug):
    blog_post = BlogPost.query.filter_by(slug=slug).first_or_404()

    if (not blog_post.is_published) and (not current_user.is_blog_author):
        return redirect(url_for("blog.index"))

    return render_template("blog/view_post.html", title=blog_post.title, blog_post=blog_post)


@bp.route("/drafts")
@login_required
def drafts():
    # Only let authorised blog authors see drafts
    if not current_user.is_blog_author:
        return redirect(url_for("blog.index"))

    draft_posts = BlogPost.query.filter_by(is_published=False).all()

    return render_template("blog/drafts.html", title="Draft Blog Posts", draft_posts=draft_posts)


@bp.route("/delete_post/<id>")
@login_required
def delete_post(id):
    # Only let authorised blog authors see drafts
    if not current_user.is_blog_author:
        return redirect(url_for("blog.index"))

    blog_post = BlogPost.query.get(int(id))
    flash("Deleted blog post {title}".format(title=blog_post.title))
    db.session.delete(blog_post)
    db.session.commit()

    return redirect(url_for("blog.drafts"))


@bp.route("/publish_post/<id>")
@login_required
def publish_post(id):
    # Only let authorised blog authors see drafts
    if not current_user.is_blog_author:
        return redirect(url_for("blog.index"))

    blog_post = BlogPost.query.get(int(id))
    blog_post.is_published = True

    flash("Published {title}".format(title=blog_post.title))
    db.session.commit()

    return redirect(url_for("blog.index"))