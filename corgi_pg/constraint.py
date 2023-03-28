import click
from .pg_common import execute

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
