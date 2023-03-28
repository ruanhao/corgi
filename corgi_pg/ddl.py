import click
from .pg_common import execute
from corgi_common.scriptutils import run_script


@click.group(help="[command group]")
@click.pass_context
def ddl(ctx):
    pass

@ddl.command(short_help='create table as')
@click.pass_context
def create_table_as(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS film_rating;
CREATE TABLE IF NOT EXISTS film_rating (rating, film_count)
AS
SELECT
    rating,
    COUNT (film_id)
FROM
    film
GROUP BY
    rating;
    """, ddl=True)

    execute(ctx, "select * from film_rating;")
    pass

@ddl.command(short_help='create table by select into')
@click.pass_context
def select_info(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS film_r;
SELECT
    film_id,
    title,
    rental_rate,
    rating
INTO TABLE film_r
FROM
    film
WHERE
    rating = 'R'
AND rental_duration = 5
ORDER BY
    title;
    """, ddl=True)

    execute(ctx, "select * from film_r;")

@ddl.command(short_help='create table')
@click.pass_context
def create_table(ctx):
    """https://www.postgresqltutorial.com/postgresql-tutorial/postgresql-create-table/"""
    execute(ctx, """
DROP TABLE IF EXISTS accounts;
CREATE TABLE accounts (
    user_id serial PRIMARY KEY,
    username VARCHAR ( 50 ) UNIQUE NOT NULL,
    password VARCHAR ( 50 ) NOT NULL,
    email VARCHAR ( 255 ) UNIQUE NOT NULL,
    created_on TIMESTAMP NOT NULL,
        last_login TIMESTAMP
);
    """)

    execute(ctx, """
DROP TABLE IF EXISTS roles;
CREATE TABLE roles(
   role_id serial PRIMARY KEY,
   role_name VARCHAR (255) UNIQUE NOT NULL
);
    """)
    # with foreign key
    execute(ctx, """
DROP TABLE IF EXISTS account_roles;
CREATE TABLE account_roles (
  user_id INT NOT NULL,
  role_id INT NOT NULL,
  grant_date TIMESTAMP,
  PRIMARY KEY (user_id, role_id),
  FOREIGN KEY (role_id)
      REFERENCES roles (role_id),
  FOREIGN KEY (user_id)
      REFERENCES accounts (user_id)
);
    """)
    pass


def _create_table_links(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS links;

CREATE TABLE links (
   link_id serial PRIMARY KEY,
   title VARCHAR (512) NOT NULL,
   url VARCHAR (1024) NOT NULL
);
    """)

@ddl.command()
@click.pass_context
def alter_table_add_column(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
ADD COLUMN active boolean;
    """)

@ddl.command()
@click.pass_context
def alter_table_drop_column(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
DROP COLUMN title;
    """)

@ddl.command()
@click.pass_context
def alter_table_rename_column(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
RENAME COLUMN title TO link_title;
    """)

@ddl.command()
@click.pass_context
def alter_table_add_column(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
ADD COLUMN target VARCHAR(10);
    """)

@ddl.command()
@click.pass_context
def alter_table_add_constraint(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
ADD CONSTRAINT unique_url UNIQUE ( url );
    """)

@ddl.command(short_help='change table name')
@click.pass_context
def alter_table_rename(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
RENAME TO urls;
    """)

@ddl.command()
@click.pass_context
def alter_table_add_check(ctx):
    _create_table_links(ctx)
    execute(ctx, """
ALTER TABLE links
ADD COLUMN target VARCHAR(10);
    """)

    execute(ctx, """
ALTER TABLE links
ADD CHECK (target IN ('_self', '_blank', '_parent', '_top'));
    """)

    try:
        execute(ctx, """
INSERT INTO links(title,url,target)
VALUES('PostgreSQL','http://www.postgresql.org/','whatever');
        """)
    except Exception as e:
        print(e)

def _create_table_contacts(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS contacts;
CREATE TABLE contacts(
    id SERIAL PRIMARY KEY,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    email VARCHAR NOT NULL UNIQUE
);

INSERT INTO contacts(first_name, last_name, email)
VALUES('John','Doe','john.doe@postgresqltutorial.com'),
      ('David','William','david.william@postgresqltutorial.com');

    """)

@ddl.command(short_help='copy table')
@click.pass_context
def copy_table(ctx):
    _create_table_contacts(ctx)
    execute(ctx, """
DROP TABLE IF EXISTS contacts_backup;
CREATE TABLE contacts_backup
AS TABLE contacts;
    """)
    # by default, do not copy indexes and constraints of the existing table.
    _rc, stdout, _stderr = run_script(f"psql postgresql://{ctx.obj['user']}:@{ctx.obj['host']}:{ctx.obj['port']}/{ctx.obj['database']}  -c '\d contacts_backup;'")
    print(stdout)
    # need to add the primary key and UNIQUE constraints to the contacts_backup table MANUALLY

    execute(ctx, """
ALTER TABLE contacts_backup ADD PRIMARY KEY(id);
ALTER TABLE contacts_backup ADD UNIQUE(email);
    """)
    _rc, stdout, _stderr = run_script(f"psql postgresql://{ctx.obj['user']}:@{ctx.obj['host']}:{ctx.obj['port']}/{ctx.obj['database']}  -c '\d contacts_backup;'")
    print(stdout)