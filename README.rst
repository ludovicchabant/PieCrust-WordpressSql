
This plugin for `PieCrust`_ lets you import a `Wordpress`_ website directly
from its SQL database, unlike the Wordpress importer that ships with PieCrust
and can only import from an XML archive.

Most of the time, your SQL database will only accept connections from
``localhost``, in which case you'll have to make an SSH tunnel between your
machine and your server's machine::

    ssh username@myserver.com -L 3307:localhost:3306 -N

Here, ``username`` is a user that has SSH access to the machine running the SQL
server -- *not* the SQL user.

This command creates a "tunnel" between port 3307 on your local machine and
port 3306 on your SQL server's machine.

Then, you can run the importer by going through the tunnel::

    chef import wordpress-sql mysql+pymysql://user:password@localhost:3307/dbname

Here, ``user`` and ``password`` *are* the credentials to the user with access
to the SQL databse. ``dbname`` is the name of the SQL database. You may also
want to pass ``--prefix`` to specify what table name prefix your Wordpress
website is using.


.. _piecrust: http://bolt80.com/piecrust/
.. _wordpress: http://www.wordpress.org

