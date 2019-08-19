"""
author: Celia M Pacheco
date: August 2019

Blogging inspired by https://charlesleifer.com/blog/how-to-make-a-flask-blog-in-one-hour-or-less/

"""


import datetime
import functools
import os
import re
import urllib
from flask import (Flask, render_template, url_for, abort, flash, Markup,
                   redirect, request, Response, session)
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.extra import ExtraExtension
from micawber import bootstrap_basic, parse_html
from micawber.cache import Cache as OEmbedCache
from peewee import *
from playhouse.flask_utils import FlaskDB, get_object_or_404, object_list
from playhouse.sqlite_ext import *

ADMIN_PASSWORD = 'secret'
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATABASE = 'sqliteext:///%s' % os.path.join(APP_DIR, 'blog.db')
DEBUG = True
SECRET_KEY = 'super secret key!' # Use for encryping cookie
SITE_WIDTH = 800

app = Flask(__name__)
app.config.from_object(__name__)

# Wrapper for configuring and referencing a PeeWee database
flask_db = FlaskDB(app)
database = flask_db.database

oembed_providers = bootstrap_basic(OEmbedCache())

class Entry(flask_db.Model):
    """
Database model for post entries. Contains two methods, save and
update_search_index.
    """
    title = CharField()
    slug = CharField(unique=True)
    content = TextField()
    published = BooleanField(index=True)
    timestamp = DateTimeField(default=datetime.datetime.now, index=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            # Creates the slug from the title
            self.slug = re.sub('[^\w]+', '-', self.title.lower())
        ret = super(Entry, self).save(*args, **kwargs)

        # Store search content
        self.update_search_index()
        return ret

    def update_search_index(self):
        search_content = '\n'.join(self.title, self.content)
        try:
            fts_entry = FTSEntry.get(FTSEntry.docid == self.id)
        except FTSEntry.DoesNotExist:
            FTSEntry.create(docid=self.id, content=search_content)
        else:
            fts_entry.content = search_content
            fts_entry.save()


    @property
    def html_content(self):
        hilite = CodeHiliteExtension(linenums=False, css_class='highlight')
        extras = ExtraExtensions()
        markdown_content = markdown(self.content, extensions=[hilite, extras])
        oembed_content = parse_html(
                markdown_content,
                oembed_providers,
                urlize_all=True,
                maxwidth=app.config['SITE_WIDTH'])
        return Markup(oembed_content)

    @classmethod
    def public(cls):
        return Entry.select().where(Entry.published == True)

    @classmethod
    def search(cls, query):
        words = [words.strip() for word in query.split() if word.strip()]
        if not words:
            return Entry.select().where(Entry.id == 0)
        else:
            search = ' '.join(words)

        return( Entry
                .select(Entry, FTSEntry.rank().alias('score'))
                .join(FTSEntry, on=(Entry.id == FTSEntry.docid))
                .where(
                    (Entry.published == True) &
                    (FTSEntry.match(search)))
                .order_by(SQL('score')))
    @classmethod
    def drafts(cls):
        return Entry.select().where(Entry.published == False)

class FTSEntry(FTSModel):
    """
Used for fast lookup?
    """
    content = SearchField()

    class Meta:
        database = database

@app.template_filter('clean_querystring')
def clean_querystring(request_args, *keys_to_remove, **new_values):
    querystring = dict((key, value) for key, value in request_args.items())
    for key in keys_to_remove:
        querystring.pop(key, None)
    querystring.update(new_values)
    return urllib.parse.urlencode(querystring)

@app.errorhandler(404)
def not_found(exc):
    return Response('<h3>Not Found </h3>'), 404

def login_required(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if session.get('logged_in'):
            return fn(*args, **kwargs)
        return redirect(url_for('login', next=request.path))
    return inner

@app.route('/login/', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next') or request.form.get('next')
    if request.method == 'POST' and request.form.get('password'):
        password = request.form.get('password')
        if password == app.config['ADMIN_PASSWORD']:
            session['logged_in'] = True
            session.permanent = True
            flash('You are now logged in.', 'success')
            return redirect(next_url or url_for('home'))
        else:
            flash('Incorrect password.', 'danger')
    return render_template('login.html', next_url=next_url)

@app.route('/logout/', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('home'))

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about/')
def about():
    return render_template('about.html', title='About')


@app.route('/blog/')
def blog():
    search_query = request.args.get('q')
    if search_query:
        query = Entry.search(search_query)
    else:
        query = Entry.public().order_by(Entry.timestamp.desc())
    return object_list('blog.html', query, search=search_query, title='Blog')

@app.route('/drafts/')
@login_required
def drafts():
    query = Entry.drafts().order_by(Entry.timestamp.desc())
    return object_list('blog.html', query)

@app.route('/create/', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        if request.form.get('title') and request.form.get('content'):
            entry = Entry.create(
                title=request.form['title'],
                content=request.form['content'],
                published=request.form.get('published') or False)
            flash('Entry created successfully,', 'success')
            if entry.published:
                return redirect(url_for('detail', slug=entry.slug))
            else:
                return redirect(url_for('edit', slug=entry.slug))
        else:
            flash('Title and Content are required.', 'danger')
    return render_template('create.html')


@app.route('/<slug>/')
def detail(slug):
    if session.get('logged_in'):
        query = Entry.select()
    else:
        query = Entry.public()
    entry = get_object_or_404(query, Entry.slug == slug)
    return render_template('detail.html', entry=entry)


@app.route('/<slug>/edit/', methods=['GET', 'POST'])
@login_required
def edit():
    entry = get_object_or_404(Entry, Entry.slug == slug)
    if request.method == 'POST':
        if request.form.get('title') and request.form.get('content'):
            entry = Entry.create(
                title=request.form['title'],
                content=request.form['content'],
                published=request.form.get('published') or False)
            flash('Entry created successfully,', 'success')
            if entry.published:
                return redirect(url_for('detail', slug=entry.slug))
            else:
                return redirect(url_for('edit', slug=entry.slug))
        else:
            flash('Title and Content are required.', 'danger')
    return render_template('edit.html')

def main():
    database.create_tables([Entry, FTSEntry])
    app.run(debug=True)


if __name__ == '__main__':
    main()
