import click
from .pg_common import execute

def _create_table_employees(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS employees;

CREATE TABLE employees (
    employee_id serial PRIMARY KEY,
    first_name VARCHAR (255),
    last_name VARCHAR (355),
    birth_date DATE NOT NULL,
    hire_date DATE NOT NULL
);

INSERT INTO employees (first_name, last_name, birth_date, hire_date)
VALUES ('Shannon','Freeman','1980-01-01','2005-01-01'),
       ('Sheila','Wells','1978-02-05','2003-01-01'),
       ('Ethel','Webb','1975-01-01','2001-01-01');
    """)

@click.group(help="[command group]")
@click.pass_context
def types(ctx):
    pass

@types.command()
@click.pass_context
def date_default_current(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS documents;

CREATE TABLE documents (
    document_id serial PRIMARY KEY,
    header_text VARCHAR (255) NOT NULL,
    posting_date DATE NOT NULL DEFAULT CURRENT_DATE
);

INSERT INTO documents (header_text)
VALUES('Billing to customer XYZ');

SELECT * FROM documents;
    """)

@types.command(short_help='show current date')
@click.pass_context
def date_current(ctx):
    execute(ctx, "SELECT NOW();")
    print()
    execute(ctx, "SELECT NOW()::date;")
    print()
    execute(ctx, 'SELECT CURRENT_DATE;')


@types.command(short_help='')
@click.pass_context
def date_format(ctx):
    # Output a PostgreSQL date value in a specific format
    execute(ctx, "SELECT TO_CHAR(NOW() :: DATE, 'dd/mm/yyyy');")
    execute(ctx, "SELECT TO_CHAR(NOW() :: DATE, 'Mon dd, yyyy');")

@types.command(short_help='')
@click.pass_context
def date_interval(ctx):
    _create_table_employees(ctx)

    execute(ctx, """
SELECT
    first_name,
    last_name,
    now() - hire_date as diff
FROM
    employees;
    """)

@types.command(short_help='calculate age in years, months, and days')
@click.pass_context
def date_age(ctx):
    _create_table_employees(ctx)
    execute(ctx, 'select * from employees;')
    execute(ctx, """
SELECT
    employee_id,
    first_name,
    last_name,
    AGE(birth_date)
FROM
    employees;
    """)

    execute(ctx, """
SELECT
    employee_id,
    first_name,
    last_name,
    AGE('2015-01-01',birth_date)
FROM
    employees;
    """)

    execute(ctx, """
SELECT
    employee_id,
    first_name,
    last_name,
    EXTRACT (YEAR FROM AGE(hire_date)) AS "work ages"
FROM
    employees;
    """)

@types.command(short_help='Extract year, quarter, month, week, day from a date value')
@click.pass_context
def date_extract(ctx):
    _create_table_employees(ctx)
    execute(ctx, """
SELECT
    employee_id,
    first_name,
    last_name,
    EXTRACT (YEAR FROM birth_date) AS YEAR,
    EXTRACT (MONTH FROM birth_date) AS MONTH,
    EXTRACT (DAY FROM birth_date) AS DAY
FROM
    employees;
    """)


@types.command()
@click.pass_context
def boolean(ctx):
    print("""
True    False
------  -------
true    false
't'     'f '
'true'  'false'
'y'     'n'
'yes'   'no'
'1'     '0'""")


@types.command()
@click.pass_context
def timestamp(ctx):
    execute(ctx, """
DROP TABLE IF EXISTS timestamp_demo;
CREATE TABLE timestamp_demo (
    ts TIMESTAMP,
    tstz TIMESTAMPTZ
);
    """)

    execute(ctx, """
INSERT INTO timestamp_demo (ts, tstz)
VALUES('2016-06-22 19:10:25+08','2016-06-22 19:10:25+08');
    """)
    execute(ctx, """
SET timezone = 'Asia/Shanghai';
SELECT
   ts, tstz
FROM
   timestamp_demo;
    """)
    execute(ctx, """
SET timezone = 'America/New_York';
SELECT
   ts, tstz
FROM
   timestamp_demo;
    """)


@types.command(short_help='timestamp functions')
@click.pass_context
def timestamp_current(ctx):
    execute(ctx, "SELECT NOW();")
    execute(ctx, "SELECT CURRENT_TIMESTAMP;")
    execute(ctx, "SELECT CURRENT_TIME;")
    execute(ctx, "SELECT TIMEOFDAY();")
    execute(ctx, "SET timezone = 'America/New_York'; SELECT TIMEOFDAY();")

@types.command(short_help='Convert between timezones')
@click.pass_context
def timestamp_timezone(ctx):
    execute(ctx, "SELECT timezone('Asia/Shanghai','2016-06-01 00:00:00+00'::timestamptz);")
    execute(ctx, "SELECT timezone('America/New_York','2016-06-01 00:00'::timestamptz);");


@types.command()
@click.pass_context
def interval(ctx):
    execute(ctx, """
SELECT
    now(),
    now() - INTERVAL '1 year 3 hours 20 minutes'
             AS "3 hours 20 minutes ago of last year";
    """)

    # output formats
    execute(ctx, """
SET intervalstyle = 'sql_standard';
SELECT
    INTERVAL '6 years 5 months 4 days 3 hours 2 minutes 1 second' AS sql_standard;
    """)
    execute(ctx, """
SET intervalstyle = 'postgres';
SELECT
    INTERVAL '6 years 5 months 4 days 3 hours 2 minutes 1 second' AS "postgres";
    """)
    execute(ctx, """
SET intervalstyle = 'postgres_verbose';
SELECT
    INTERVAL '6 years 5 months 4 days 3 hours 2 minutes 1 second' AS "postgres_verbose";
    """)
#     execute(ctx, """
# SET intervalstyle = 'iso_8601';
# SELECT
#     INTERVAL '6 years 5 months 4 days 3 hours 2 minutes 1 second';
#     """)
    pass

@types.command()
@click.pass_context
def uuid(ctx):
    execute(ctx, """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    """)

    execute(ctx, "SELECT uuid_generate_v1();")
    execute(ctx, "SELECT uuid_generate_v4();")