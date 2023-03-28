import click
from .pg_common import execute, select_all
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

@ddl.command(short_help='create table with array column')
@click.pass_context
def create_table_array(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS contacts;
CREATE TABLE contacts (
    id serial PRIMARY KEY,
    name VARCHAR (100),
    phones TEXT []
);
    """)
    # insert
    execute(ctx, """
INSERT INTO contacts (name, phones)
VALUES
    ('Lily Bush','{"(408)-589-5841"}'),
    ('William Gate','{"(408)-589-5842","(408)-589-58423"}'),
    ('John Doe',ARRAY [ '(408)-589-5846','(408)-589-5555' ]);
    """)
    # query
    select_all(ctx, 'contacts')
    execute(ctx, """
SELECT
    name,
--get first phone number
    phones [ 1 ]
FROM
    contacts;
    """)
    execute(ctx, """
SELECT
    name
FROM
    contacts
WHERE
    phones [ 2 ] = '(408)-589-58423';
    """)

    # modifying
    execute(ctx, """
UPDATE contacts
SET phones [2] = '(408)-589-5843'
WHERE name = 'William Gate';
    """)

    # Search in PostgreSQL Array
    execute(ctx, """
SELECT
    name,
    phones
FROM
    contacts
WHERE
    '(408)-589-5555' = ANY (phones);
    """)

    # expand array
    execute(ctx, """
SELECT
    id,
    name,
    unnest(phones)
FROM
    contacts;
    """)
    pass

@ddl.command(short_help='create table with UUID column')
@click.pass_context
def create_table_uuid(ctx):
    execute(ctx, """CREATE EXTENSION IF NOT EXISTS "uuid-ossp";""")

    execute(ctx, """
DROP TABLE IF EXISTS contacts;
CREATE TABLE contacts (
    contact_id uuid DEFAULT uuid_generate_v4 (),
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    phone VARCHAR,
    PRIMARY KEY (contact_id)
);
INSERT INTO contacts (
    first_name,
    last_name,
    email,
    phone
)
VALUES
    (
        'John',
        'Smith',
        'john.smith@example.com',
        '408-237-2345'
    ),
    (
        'Jane',
        'Smith',
        'jane.smith@example.com',
        '408-237-2344'
    ),
    (
        'Alex',
        'Smith',
        'alex.smith@example.com',
        '408-237-2343'
    );
    """)
    select_all(ctx, "contacts")

@ddl.command(short_help='create table with json column')
@click.pass_context
def create_table_json(ctx):
    """https://www.postgresql.org/docs/current/functions-json.html"""
    execute(ctx, """
DROP TABLE IF EXISTS orders;
CREATE TABLE orders (
    id serial NOT NULL PRIMARY KEY,
    info jsonb NOT NULL
);

INSERT INTO orders (info)
VALUES('{ "customer": "John Doe", "items": {"product": "Beer","qty": 6}}');

INSERT INTO orders (info)
VALUES('{ "customer": "Lily Bush", "items": {"product": "Diaper","qty": 24}}'),
      ('{ "customer": "Josh William", "items": {"product": "Toy Car","qty": 1}}'),
      ('{ "customer": "Mary Clark", "items": {"product": "Toy Train","qty": 2}}');
    """)

    execute(ctx, "SELECT info FROM orders;")
    print()
    print("-> returns JSON object field by key in form of JSON:")
    execute(ctx, """
SELECT info -> 'customer' AS customer
FROM orders;
    """)

    print()
    print("-> returns JSON object field by key in form of text:")
    execute(ctx, """
SELECT info ->> 'customer' AS customer
FROM orders;
    """)

    print()
    print("-> returns JSON object field by key chain:")
    execute(ctx, """
SELECT info -> 'items' ->> 'product' as product
FROM orders
ORDER BY product;
    """)

    print()
    print("-> Use JSON operator in WHERE clause:")
    execute(ctx, """
SELECT info ->> 'customer' AS customer,
    info -> 'items' ->> 'product' AS product
FROM orders
WHERE CAST ( info -> 'items' ->> 'qty' AS INTEGER) = 2
    """)

    print()
    print("-> Apply aggregate functions to JSON data:")
    execute(ctx, """
SELECT
   MIN (CAST (info -> 'items' ->> 'qty' AS INTEGER)),
   MAX (CAST (info -> 'items' ->> 'qty' AS INTEGER)),
   SUM (CAST (info -> 'items' ->> 'qty' AS INTEGER)),
   AVG (CAST (info -> 'items' ->> 'qty' AS INTEGER))
FROM orders;
    """)

@ddl.command(short_help='create table with hstore column')
@click.pass_context
def create_table_hstore(ctx):
    execute(ctx, """CREATE EXTENSION IF NOT EXISTS hstore;""")

    execute(ctx, """
DROP TABLE IF EXISTS books;
CREATE TABLE books (
    id serial primary key,
    title VARCHAR (255),
    attr hstore
);

INSERT INTO books (title, attr)
VALUES
    (
        'PostgreSQL Tutorial',
        '"paperback" => "243",
         "publisher" => "postgresqltutorial.com",
         "language"  => "English",
         "ISBN-13"   => "978-1449370000",
         "weight"    => "11.2 ounces"'
    ),
    (
        'PostgreSQL Cheat Sheet',
        '
"paperback" => "5",
"publisher" => "postgresqltutorial.com",
"language"  => "English",
"ISBN-13"   => "978-1449370001",
"weight"    => "1 ounces"'
    );
    """)

    execute(ctx, "SELECT attr FROM books;")
    # Query value for a specific key
    execute(ctx, """
SELECT
    attr -> 'ISBN-13' AS isbn
FROM
    books;
    """)
    # where clause
    execute(ctx, """
SELECT
    title, attr -> 'weight' AS weight
FROM
    books
WHERE
    attr -> 'ISBN-13' = '978-1449370000';
    """)

    # Add/Update key-value pairs to existing rows
    execute(ctx, """
UPDATE books
SET attr = attr || '"freeshipping"=>"yes"' :: hstore;
    """)
    select_all(ctx, 'books')

    # remove
    execute(ctx, """
UPDATE books
SET attr = delete(attr, 'freeshipping');
    """)
    select_all(ctx, 'books')

    # check key existence
    execute(ctx, """
SELECT
  title,
  attr->'publisher' as publisher,
  attr
FROM
    books
WHERE
    attr ? 'publisher';
    """)

    # check key-value pair
    # retrieves all rows which 'attr' column contains a key-value pair that matches "weight"=>"11.2 ounces"
    execute(ctx, """
SELECT
    title
FROM
    books
WHERE
    attr @> '"weight"=>"11.2 ounces"' :: hstore;
    """)

    print("-> Query rows that contain multiple specified keys:")
    execute(ctx, """
SELECT
    title,
    attr
FROM
    books
WHERE
    attr ?& ARRAY [ 'language', 'weight' ];
    """)
    print("-> Query rows that contain ANY of specified keys:")
    execute(ctx, """
SELECT
    title,
    attr
FROM
    books
WHERE
    attr ?| ARRAY [ 'language', 'weight' ];
    """)

    print("-> Get all keys(akeys):")
    execute(ctx, """
SELECT
    akeys (attr)
FROM
    books;
    """)
    print("-> Get all keys as set(skeys):")
    execute(ctx, """
SELECT
    skeys (attr)
FROM
    books;
    """)

    print("-> Get all values(avals):")
    execute(ctx, """
SELECT
    avals (attr)
FROM
    books;
    """)
    print("-> Get all values as set(svals):")
    execute(ctx, """
SELECT
    svals (attr)
FROM
    books;
    """)

    print("-> Convert hstore to json:")
    execute(ctx, """
SELECT
  title,
  hstore_to_json (attr) json
FROM
  books;
    """)

    print("-> Convert hstore to set:")
    execute(ctx, """
SELECT
    title,
    (EACH(attr) ).*
FROM
    books;
    """)

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
