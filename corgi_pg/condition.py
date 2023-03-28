import click
from .pg_common import execute as e

@click.group(help="[command group]")
@click.pass_context
def condition(ctx):
    pass

@condition.command()
@click.pass_context
def case_select(ctx):
    e(ctx, """
SELECT title,
       length,
       CASE
           WHEN length> 0 AND length <= 50 THEN 'Short'
           WHEN length > 50 AND length <= 120 THEN 'Medium'
           WHEN length> 120 THEN 'Long'
       END AS duration
FROM film
ORDER BY title;
    """)


@condition.command()
@click.pass_context
def case_aggregate(ctx):
    e(ctx, """
SELECT
    SUM (CASE
         WHEN rental_rate = 0.99 THEN 1
         ELSE 0
         END
    ) AS "Economy",
    SUM (
        CASE
        WHEN rental_rate = 2.99 THEN 1
        ELSE 0
        END
    ) AS "Mass",
    SUM (
        CASE
        WHEN rental_rate = 4.99 THEN 1
        ELSE 0
        END
    ) AS "Premium"
FROM
    film;
    """)


@condition.command(short_help='test colaesce')
@click.pass_context
def colaesce(ctx):
    """often use the COLAESCE function to substitute a default value for null values when we querying the data"""
    e(ctx, """
DROP TABLE IF EXISTS items;
CREATE TABLE items (
    ID serial PRIMARY KEY,
    product VARCHAR (100) NOT NULL,
    price NUMERIC NOT NULL,
    discount NUMERIC
);
INSERT INTO items (product, price, discount)
VALUES
    ('A', 1000 ,10),
    ('B', 1500 ,20),
    ('C', 800 ,5),
    ('D', 500, NULL);
    """)

    print("-> not using COALESCE:")
    e(ctx, """
SELECT
    product,
    (price - discount) AS net_price
FROM
    items;
    """)

    print("-> using COALESCE:")
    e(ctx, '''
SELECT
    product,
    (price - COALESCE(discount,0)) AS net_price
FROM
    items;
    ''')
