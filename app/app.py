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
from flask import (Flask, render_template, url_for, abort, flash, Markup
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
DATABASE = 'sqliteext://%s' % os.path.join(APP_DIR, 'blog.db')
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


class FTSEntry(FTSModel):
    """
Used for fast lookup?
    """
    content = SearchField()

    class Meta:
        database = database
@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html')

@app.route("/about")
def about():
    return render_template('about.html', title='About')


if __name__ == '__main__':
    app.run(debug=True)

