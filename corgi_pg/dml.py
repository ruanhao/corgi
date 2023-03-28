import click
from .pg_common import execute
from datetime import datetime

@click.group(help="[command group]")
@click.pass_context
def dml(ctx):
    pass

def _create_table_product(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS product_execute;
CREATE TABLE product_segment (
    id SERIAL PRIMARY KEY,
    segment VARCHAR NOT NULL,
    discount NUMERIC (4, 2)
);


INSERT INTO
    product_segment (segment, discount)
VALUES
    ('Grand Luxury', 0.05),
    ('Luxury', 0.06),
    ('Mass', 0.1);

DROP TABLE IF EXISTS product;
CREATE TABLE product(
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    price NUMERIC(10,2),
    net_price NUMERIC(10,2),
    segment_id INT NOT NULL,
    FOREIGN KEY(segment_id) REFERENCES product_segment(id)
);


INSERT INTO
    product (name, price, segment_id)
VALUES
    ('diam', 804.89, 1),
    ('vestibulum aliquet', 228.55, 3),
    ('lacinia erat', 366.45, 2),
    ('scelerisque quam turpis', 145.33, 3),
    ('justo lacinia', 551.77, 2),
    ('ultrices mattis odio', 261.58, 3),
    ('hendrerit', 519.62, 2),
    ('in hac habitasse', 843.31, 1),
    ('orci eget orci', 254.18, 3),
    ('pellentesque', 427.78, 2),
    ('sit amet nunc', 936.29, 1),
    ('sed vestibulum', 910.34, 1),
    ('turpis eget', 208.33, 3),
    ('cursus vestibulum', 985.45, 1),
    ('orci nullam', 841.26, 1),
    ('est quam pharetra', 896.38, 1),
    ('posuere', 575.74, 2),
    ('ligula', 530.64, 2),
    ('convallis', 892.43, 1),
    ('nulla elit ac', 161.71, 3);
    """)

def _create_table_courses(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS courses;

CREATE TABLE courses(
    course_id serial primary key,
    course_name VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    published_date date
);

INSERT INTO
    courses(course_name, description, published_date)
VALUES
    ('PostgreSQL for Developers','A complete PostgreSQL for Developers','2020-07-13'),
    ('PostgreSQL Admininstration','A PostgreSQL Guide for DBA',NULL),
    ('PostgreSQL High Performance',NULL,NULL),
    ('PostgreSQL Bootcamp','Learn PostgreSQL via Bootcamp','2013-07-11'),
    ('Mastering PostgreSQL','Mastering PostgreSQL in 21 Days','2012-06-30');
    """)

@dml.command(short_help='syntax')
def update():
    """\b
UPDATE table_name
SET column1 = value1,
    column2 = value2,
    ...
WHERE condition;
    """
    pass

@dml.command(short_help='update one record')
@click.pass_context
def update_one(ctx):
    _create_table_courses(ctx)
    print("BEFORE")

    execute(ctx, """
SELECT * FROM courses;
    """)

    execute(ctx, """
UPDATE courses
SET published_date = '2020-08-01'
WHERE course_id = 3;
    """)
    print("AFTER")
    execute(ctx, """
SELECT * FROM courses;
    """)
    pass

@dml.command()
@click.pass_context
def update_and_returning(ctx):
    _create_table_courses(ctx)
    execute(ctx, """
UPDATE courses
SET published_date = '2020-07-01'
WHERE course_id = 2
RETURNING *;
    """)

@dml.command(help='update data in a table based on values in another table')
@click.pass_context
def update_join(ctx):
    _create_table_product(ctx)
    # use join statement to update data in a table based on values in another table.
    execute(ctx, """
UPDATE product
SET net_price = price - price * discount
FROM product_segment
WHERE product.segment_id = product_segment.id;
    """)
    execute(ctx, 'select * from product')


@dml.command(short_help="insert syntax")
@click.pass_context
def insert(ctx):
    """
    \b
    INSERT INTO table_name(column1, column2, …)
    VALUES (value1, value2, …);"""
    pass

@dml.command()
@click.pass_context
def insert_and_returning(ctx):
    execute(ctx, """
    DROP TABLE IF EXISTS links;

CREATE TABLE links (
    id SERIAL PRIMARY KEY,
    url VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR (255),
        last_update DATE
);
    """)
    # To get the last insert id from inserted row, you use the RETURNING clause of the INSERTstatement.
    execute(ctx, """
    INSERT INTO links (url, name)
VALUES('http://www.postgresql.org','PostgreSQL')
RETURNING id;
    """)
    pass

@dml.command()
@click.pass_context
def insert_multiple(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS links;

CREATE TABLE links (
    id SERIAL PRIMARY KEY,
    url VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(255)
);
    """)
    # To get the last insert id from inserted row, you use the RETURNING clause of the INSERTstatement.
    execute(ctx, """
INSERT INTO
    links (url, name)
VALUES
    ('https://www.google.com','Google'),
    ('https://www.yahoo.com','Yahoo'),
    ('https://www.bing.com','Bing');
    """)
    execute(ctx, "select * from links;")
    pass

@dml.command()
@click.pass_context
def insert_multiple_and_returning(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS links;

CREATE TABLE links (
    id SERIAL PRIMARY KEY,
    url VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(255)
);
    """)

    execute(ctx, """
INSERT INTO
    links(url,name, description)
VALUES
    ('https://duckduckgo.com/','DuckDuckGo','Privacy & Simplified Search Engine'),
    ('https://swisscows.com/','Swisscows','Privacy safe WEB-search')
RETURNING *;
    """)
    pass

def _create_table_customers(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id serial PRIMARY KEY,
    name VARCHAR UNIQUE,
    email VARCHAR NOT NULL,
    active bool NOT NULL DEFAULT TRUE
);

INSERT INTO
    customers (name, email)
VALUES
    ('IBM', 'contact@ibm.com'),
    ('Microsoft', 'contact@microsoft.com'),
    ('Intel', 'contact@intel.com');
    """)

@dml.command()
@click.pass_context
def insert_on_conflict_do_nothing(ctx):
    _create_table_customers(ctx)
    execute(ctx, """
INSERT INTO customers (NAME, email)
VALUES('Microsoft','hotline@microsoft.com')
ON CONFLICT (name)
DO NOTHING;
    """)
    execute(ctx, "select * from customers;")
    pass

@dml.command()
@click.pass_context
def insert_on_conflict_do_update(ctx):
    _create_table_customers(ctx)
    # concatenate the new email with the old email when inserting a customer that already exists
    execute(ctx, """
INSERT INTO customers (name, email)
VALUES('Microsoft','hotline@microsoft.com')
ON CONFLICT (name)
DO
   UPDATE SET email = EXCLUDED.email || ';' || customers.email;
    """)
    execute(ctx, "select * from customers;")
    pass

@dml.command()
@click.pass_context
def delete_duplicates(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS basket;
CREATE TABLE basket(
    id SERIAL PRIMARY KEY,
    fruit VARCHAR(50) NOT NULL
);
INSERT INTO basket(fruit) values('apple');
INSERT INTO basket(fruit) values('apple');

INSERT INTO basket(fruit) values('orange');
INSERT INTO basket(fruit) values('orange');
INSERT INTO basket(fruit) values('orange');

INSERT INTO basket(fruit) values('banana');
    """)

    execute(ctx, """
SELECT
    id,
    fruit
FROM
    basket;
    """)

    execute(ctx, """
DELETE FROM
    basket a
        USING basket b
WHERE
    a.id < b.id
    AND a.fruit = b.fruit;
    """)

    execute(ctx, """
SELECT
    id,
    fruit
FROM
    basket;
    """)
