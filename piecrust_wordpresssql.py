import logging
from urllib.parse import urlparse
from collections import OrderedDict
from sqlalchemy import (
        Table, MetaData,
        Column, Integer, String, DateTime,
        ForeignKey,
        create_engine)
from sqlalchemy.sql import select, join
from piecrust.plugins.base import PieCrustPlugin
from piecrust.importing.wordpress import WordpressImporterBase, _ImporterBase


logger = logging.getLogger(__name__)


class _Plugin(PieCrustPlugin):
    name = 'WordpressSQL'

    def getImporters(self):
        return [
                WordpressSQLImporter()]


__piecrust_plugin__ = _Plugin


class _ImportContext(object):
    def __init__(self):
        self.conn = None
        self.options = None
        self.users = None
        self.posts = None
        self.term_relationships = None
        self.term_taxonomy = None
        self.terms = None


class WordpressSQLImporter(WordpressImporterBase):
    name = 'wordpress-sql'
    description = "Imports a Wordpress blog from its SQL database."

    def setupParser(self, parser, app):
        super(WordpressSQLImporter, self).setupParser(parser, app)
        parser.add_argument(
                '--prefix',
                default="wp_",
                help="The SQL table prefix. Defaults to `wp_`.")
        parser.add_argument(
                'db_url',
                help=("The URL of the SQL database.\n"
                      "It should be of the form:  "
                      "type://user:password@server/database\n"
                      "\n"
                      "For example:\n"
                      "mysql://user:password@example.org/my_database"))

    def _getImplementation(self, app, args):
        return _SqlImporter(app, args)


class _SqlImporter(_ImporterBase):
    def __init__(self, app, args):
        super(_SqlImporter, self).__init__(app, args)
        self.db_url = args.db_url
        self.prefix = args.prefix

    def _open(self):
        parsed_url = urlparse(self.db_url)
        logger.info("Connecting to %s as %s..." % (
                    parsed_url.hostname, parsed_url.username))
        engine = create_engine(self.db_url)
        conn = engine.connect()

        metadata = MetaData()
        options = Table(
                self.prefix + 'options', metadata,
                Column('option_name', String),
                Column('option_value', String))
        users = Table(
                self.prefix + 'users', metadata,
                Column('ID', Integer, primary_key=True),
                Column('user_login', String),
                Column('user_nicename', String),
                Column('user_email', String),
                Column('user_url', String),
                Column('display_name', String))
        posts = Table(
                self.prefix + 'posts', metadata,
                Column('ID', Integer, primary_key=True),
                Column('post_author', Integer,
                       ForeignKey(self.prefix + 'users.ID')),
                Column('post_date', DateTime),
                Column('post_content', String),
                Column('post_title', String),
                Column('post_excerpt', String),
                Column('post_status', String),
                Column('post_name', String),
                Column('guid', String),
                Column('post_type', String))
        term_rel = Table(
                self.prefix + 'term_relationships', metadata,
                Column('object_id', Integer,
                       ForeignKey(self.prefix + 'posts.ID')),
                Column('term_taxonomy_id', Integer,
                       ForeignKey(self.prefix +
                                  'term_taxonomy.term_taxonomy_id')))
        term_tax = Table(
                self.prefix + 'term_taxonomy', metadata,
                Column('term_taxonomy_id', Integer, primary_key=True),
                Column('term_id', Integer,
                       ForeignKey(self.prefix + 'terms.term_id')),
                Column('taxonomy', String),
                Column('description', String),
                Column('parent', Integer))
        terms = Table(
                self.prefix + 'terms', metadata,
                Column('term_id', Integer, primary_key=True),
                Column('name', String),
                Column('slug', String),
                Column('term_group', Integer))

        ctx = _ImportContext()
        ctx.conn = conn
        ctx.options = options
        ctx.users = users
        ctx.posts = posts
        ctx.term_relationships = term_rel
        ctx.term_taxonomy = term_tax
        ctx.terms = terms
        return ctx

    def _close(self, ctx):
        ctx.conn.close()

    def _getSiteConfig(self, ctx):
        conn = ctx.conn

        # Get basic stuff.
        res = conn.execute(
                select([ctx.options])
                .where(ctx.options.c.option_name == 'blogname')).fetchone()
        title = res['option_value']
        res = (conn.execute(
                    select([ctx.options])
                    .where(ctx.options.c.option_name == 'blogdescription'))
               .fetchone())
        description = res['option_value']
        site_config = OrderedDict({
                'site': {
                    'title': title,
                    'description': description}
                })

        res = conn.execute(select([ctx.users]))
        authors = {}
        for row in res:
            auth_id = int(row['ID'])
            auth_login = row['user_login']
            authors[auth_login] = {
                    'email': row['user_email'],
                    'display_name': row['display_name'],
                    'author_id': auth_id}
        site_config['site']['authors'] = authors

        return site_config

    def _getPosts(self, ctx):
        res = ctx.conn.execute(select([ctx.posts]))
        for row in res:
            post_type = row['post_type']
            if post_type == 'attachment':
                yield self._getAssetInfo(row)
            elif post_type in ['post', 'page']:
                yield self._getPostInfo(ctx, row)
            elif post_type in ['revision']:
                continue
            else:
                raise Exception("Unknown post type: %s" % post_type)

    def _getAssetInfo(self, row):
        url = row['guid']
        return {'type': 'attachment', 'url': url}

    def _getPostInfo(self, ctx, row):
        post_info = {
                'type': row['post_type'],
                'slug': row['post_name'],
                'datetime': row['post_date'],
                'title': row['post_title'],
                'status': row['post_status'],
                'post_id': row['ID'],
                'post_guid': row['guid'],
                'content': row['post_content'],
                'excerpt': row['post_excerpt']}

        res = ctx.conn.execute(
                select([ctx.users])
                .where(ctx.users.c.ID == row['post_author'])).fetchone()
        if res:
            post_info['author'] = res['user_login']
        else:
            logger.warning("No author on %s" % row['post_name'])
            post_info['author'] = ''

        # TODO: This is super slow. Gotta cache this thing somehow.
        res = ctx.conn.execute(
                join(ctx.term_relationships,
                     join(ctx.term_taxonomy, ctx.terms))
                .select(ctx.term_relationships.c.object_id == row['ID']))
        categories = []
        for r in res:
            if r['taxonomy'] != 'category':
                logger.debug("Skipping taxonomy '%s' on: %s" %
                             (r['taxonomy'], row['post_name']))
                continue
            categories.append(r['slug'])
        post_info['categories'] = categories

        metadata = {}
        post_info['metadata'] = metadata

        return post_info

