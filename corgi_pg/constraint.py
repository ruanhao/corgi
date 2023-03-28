import click
from .pg_common import execute
from corgi_common.scriptutils import run_script

def _create_table_check(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS employees;
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR (50),
    last_name VARCHAR (50),
    birth_date DATE CONSTRAINT valid_birth_date CHECK (
        birth_date > '1900-01-01'
        AND birth_date < '2046-01-01'
    ),
    joined_date DATE CONSTRAINT valic_joined_date CHECK (joined_date > birth_date),
    salary numeric CONSTRAINT positive_salary CHECK(salary > 0)
);
    """)

def _create_table_fk_cascade(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS contacts;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers(
   customer_id INT GENERATED ALWAYS AS IDENTITY,
   customer_name VARCHAR(255) NOT NULL,
   PRIMARY KEY(customer_id)
);

CREATE TABLE contacts(
   contact_id INT GENERATED ALWAYS AS IDENTITY,
   customer_id INT,
   contact_name VARCHAR(255) NOT NULL,
   phone VARCHAR(15),
   email VARCHAR(100),
   PRIMARY KEY(contact_id),
   CONSTRAINT fk_customer
      FOREIGN KEY(customer_id)
      REFERENCES customers(customer_id)
      ON DELETE CASCADE
);

INSERT INTO customers(customer_name)
VALUES('BlueBird Inc'),
      ('Dolphin LLC');

INSERT INTO contacts(customer_id, contact_name, phone, email)
VALUES(1,'John Doe','(408)-111-1234','john.doe@bluebird.dev'),
      (1,'Jane Doe','(408)-111-1235','jane.doe@bluebird.dev'),
      (2,'David Wright','(408)-222-1234','david.wright@dolphin.dev');
    """)

def _create_table_fk_set_null(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS contacts;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers(
   customer_id INT GENERATED ALWAYS AS IDENTITY,
   customer_name VARCHAR(255) NOT NULL,
   PRIMARY KEY(customer_id)
);

CREATE TABLE contacts(
   contact_id INT GENERATED ALWAYS AS IDENTITY,
   customer_id INT,
   contact_name VARCHAR(255) NOT NULL,
   phone VARCHAR(15),
   email VARCHAR(100),
   PRIMARY KEY(contact_id),
   CONSTRAINT fk_customer
      FOREIGN KEY(customer_id)
      REFERENCES customers(customer_id)
      ON DELETE SET NULL
);

INSERT INTO customers(customer_name)
VALUES('BlueBird Inc'),
      ('Dolphin LLC');

INSERT INTO contacts(customer_id, contact_name, phone, email)
VALUES(1,'John Doe','(408)-111-1234','john.doe@bluebird.dev'),
      (1,'Jane Doe','(408)-111-1235','jane.doe@bluebird.dev'),
      (2,'David Wright','(408)-222-1234','david.wright@dolphin.dev');
    """)

def _create_table_fk_no_action(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS contacts;

CREATE TABLE customers(
   customer_id INT GENERATED ALWAYS AS IDENTITY,
   customer_name VARCHAR(255) NOT NULL,
   PRIMARY KEY(customer_id)
);

CREATE TABLE contacts(
   contact_id INT GENERATED ALWAYS AS IDENTITY,
   customer_id INT,
   contact_name VARCHAR(255) NOT NULL,
   phone VARCHAR(15),
   email VARCHAR(100),
   PRIMARY KEY(contact_id),
   CONSTRAINT fk_customer
      FOREIGN KEY(customer_id)
      REFERENCES customers(customer_id)
);

INSERT INTO customers(customer_name)
VALUES('BlueBird Inc'),
      ('Dolphin LLC');

INSERT INTO contacts(customer_id, contact_name, phone, email)
VALUES(1,'John Doe','(408)-111-1234','john.doe@bluebird.dev'),
      (1,'Jane Doe','(408)-111-1235','jane.doe@bluebird.dev'),
      (2,'David Wright','(408)-222-1234','david.wright@dolphin.dev');
    """)

@click.group(help="[command group]")
@click.pass_context
def constraint(ctx):
    pass

@constraint.command()
@click.pass_context
def fk_no_action(ctx):
    _create_table_fk_no_action(ctx)
    # PostgreSQL issues a constraint violation because the referencing rows of the customer id 1 still exist in the contacts table:
    try:
        execute(ctx, "DELETE FROM customers WHERE customer_id = 1;")
    except Exception as e:
        print(e)
    pass

@constraint.command()
@click.pass_context
def fk_set_null(ctx):
    _create_table_fk_set_null(ctx)
    execute(ctx, "select * from contacts;")
    execute(ctx, "DELETE FROM customers WHERE customer_id = 1;")
    execute(ctx, "select * from contacts;")
    pass

@constraint.command()
@click.pass_context
def fk_on_delete_cascade(ctx):
    _create_table_fk_cascade(ctx)
    execute(ctx, "select * from contacts;")
    execute(ctx, "DELETE FROM customers WHERE customer_id = 1;")
    execute(ctx, "select * from contacts;")
    pass

@constraint.command()
@click.pass_context
def check(ctx):
    _create_table_check(ctx)
    try:
        execute(ctx, """
INSERT INTO employees (first_name, last_name, birth_date, joined_date, salary)
VALUES ('John', 'Doe', '1972-01-01', '2015-07-01', - 100000);
        """)
    except Exception as e:
        print(e)

@constraint.command()
@click.pass_context
def check_not_all_null(ctx):
    # want either username or email column of the user tables is not null or empty
    execute(ctx, """
DROP TABLE IF EXISTS users;
CREATE TABLE users (
 id serial PRIMARY KEY,
 username VARCHAR (50),
 password VARCHAR (50),
 email VARCHAR (50),
 CONSTRAINT username_email_notnull CHECK (
   NOT (
     ( username IS NULL  OR  username = '' )
     AND
     ( email IS NULL  OR  email = '' )
   )
 )
);
    """)
    # The following statement works.
    execute(ctx, """
INSERT INTO users (username, email)
VALUES
    ('user1', NULL),
    (NULL, 'email1@example.com'),
    ('user2', 'email2@example.com'),
    ('user3', '');
    """)

    # violates the CHECK constraint:
    try:
        execute(ctx, """
INSERT INTO users (username, email)
VALUES
    (NULL, NULL),
    (NULL, ''),
    ('', NULL),
    ('', '');
        """)
    except Exception as e:
        print(e)



@constraint.command()
@click.pass_context
def unique(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS person;
CREATE TABLE person (
    id SERIAL  PRIMARY KEY,
    first_name VARCHAR (50),
    last_name  VARCHAR (50),
    email      VARCHAR (50),
    UNIQUE(email)
);
    """)

@constraint.command(short_help='Adding unique constraint using a unique index')
@click.pass_context
def unique_using_index(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS equipment;
CREATE TABLE equipment (
    id SERIAL PRIMARY KEY,
    name VARCHAR (50) NOT NULL,
    equip_id VARCHAR (16) NOT NULL
);
    """)

    _rc, stdout, _stderr = run_script(f"psql postgresql://{ctx.obj['user']}:@{ctx.obj['host']}:{ctx.obj['port']}/{ctx.obj['database']}  -c '\d equipment;'")
    print(stdout)

    # create a unique index based on the 'equip_id' column.
    execute(ctx, """
--CREATE UNIQUE INDEX CONCURRENTLY equipment_equip_id
CREATE UNIQUE INDEX equipment_equip_id
ON equipment (equip_id);
    """)
    # add a unique constraint to the 'equipment' table using the 'equipment_equip_id' index
    execute(ctx, """
ALTER TABLE equipment
ADD CONSTRAINT unique_equip_id
UNIQUE USING INDEX equipment_equip_id;
    """)

    _rc, stdout, _stderr = run_script(f"psql postgresql://{ctx.obj['user']}:@{ctx.obj['host']}:{ctx.obj['port']}/{ctx.obj['database']}  -c '\d equipment;'")
    print(stdout)
