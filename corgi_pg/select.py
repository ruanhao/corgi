import click
from .pg_common import execute
from datetime import datetime


@click.group(help="[command group]")
@click.pass_context
def select(ctx):
    pass

@select.command(short_help="concatenate columns")
@click.pass_context
def concatenation(ctx):
    execute(
        ctx,
        """
SELECT
   first_name || ' ' || last_name AS "full name",
   email
FROM
   customer
LIMIT 10
        """)
    pass

@select.command()
@click.pass_context
def orderby(ctx):
    execute(
        ctx,
        """
SELECT
    first_name,
    last_name
FROM
    customer
ORDER BY
    first_name ASC,
    last_name  DESC
LIMIT 10
        """)
    pass

@select.command()
@click.pass_context
def orderby_expression(ctx):
    execute(
        ctx,
        """
SELECT
    first_name,
    LENGTH(first_name) AS len
FROM
    customer
ORDER BY
    len DESC
LIMIT 10
        """)
    pass

@select.command()
@click.pass_context
def orderby_nullsfirst(ctx):
    """Use NULLS FIRST and NULLS LAST options to explicitly specify the order of NULL with other non-null values.
    """
    table_name = f"sort_demo_{int(datetime.now().timestamp())}"
    execute(
        ctx,
        f"""
-- create a new table
CREATE TABLE {table_name}(
    num INT
);

-- insert some data
INSERT INTO {table_name}(num)
VALUES(1),(2),(3),(null);
        """)
    execute(
        ctx,
        f"""
SELECT num
FROM {table_name}
ORDER BY num NULLS FIRST;
        """
    )
    pass

@select.command()
@click.pass_context
def where_in(ctx):
    execute(
        ctx,
        """
SELECT
    first_name,
    last_name
FROM
    customer
WHERE
    first_name IN ('Ann','Anne','Annie');
        """)

@select.command()
@click.pass_context
def where_like(ctx):
    """The % is called a wildcard that matches any string.
    """
    execute(
        ctx,
        """
SELECT
    first_name,
    last_name
FROM
    customer
WHERE
    first_name LIKE 'Ann%'
        """)

@select.command()
@click.pass_context
def where_between(ctx):
    execute(
        ctx,
        """
SELECT
    first_name,
    LENGTH(first_name) AS name_length
FROM
    customer
WHERE
    first_name LIKE 'A%' AND
    LENGTH(first_name) BETWEEN 3 AND 5
ORDER BY
    name_length;
        """)


@select.command()
@click.pass_context
def limit_offset(ctx):
    execute(
        ctx,
        """
SELECT
    film_id,
    title,
    release_year
FROM
    film
ORDER BY
    film_id
LIMIT 4 OFFSET 3;
        """)


@select.command()
@click.pass_context
def cast_as_date(ctx):
    execute(
        ctx,
        """
SELECT *
FROM rental
WHERE CAST (return_date AS DATE) = '2005-05-27'
ORDER BY customer_id
LIMIT 5;
        """)


@select.command()
@click.pass_context
def subquery_exists(ctx):
    execute(
        ctx,
        """
SELECT
    first_name,
    last_name
FROM
    customer
WHERE
    EXISTS (
        SELECT
            1
        FROM
            payment
        WHERE
            payment.customer_id = customer.customer_id
    );
        """)

@select.command()
@click.pass_context
def subquery_any(ctx):
    print("Maximum length of film grouped by film category:")
    execute(
        ctx,
        """
    SELECT MAX( length )
    FROM film
    INNER JOIN film_category USING(film_id)
    GROUP BY  category_id;
        """)

    print()
    print("Finds the films whose lengths are greater than or equal to the maximum length of ANY film category:")
    execute(
        ctx,
        """
SELECT title, length
FROM film
WHERE length >= ANY(
    SELECT MAX( length )
    FROM film
    INNER JOIN film_category USING(film_id)
    GROUP BY  category_id );
        """)

@select.command()
@click.pass_context
def subquery_all(ctx):
    print("The following query returns the average lengths of all films grouped by film rating:")
    execute(
        ctx,
        """
SELECT
    ROUND(AVG(length), 2) avg_length
FROM
    film
GROUP BY
    rating
ORDER BY
    avg_length DESC;
        """)

    print()
    print("To find all films whose lengths are greater than the list of the average lengths above:")
    execute(
        ctx,
        """
SELECT
    film_id,
    title,
    length
FROM
    film
WHERE
    length > ALL (
            SELECT
                ROUND(AVG (length),2)
            FROM
                film
            GROUP BY
                rating
    )
ORDER BY
    length;

        """)

@select.command()
@click.pass_context
def cte_simple(ctx):
    # return only films whose lengths are 'Long'.
    execute(
        ctx,
        """
WITH cte_film AS (
    SELECT
        film_id,
        title,
        (CASE
            WHEN length < 30 THEN 'Short'
            WHEN length < 90 THEN 'Medium'
            ELSE 'Long'
        END) length
    FROM
        film
)
SELECT
    film_id,
    title,
    length
FROM
    cte_film
WHERE
    length = 'Long'
ORDER BY
    title;
        """)


@select.command()
@click.pass_context
def cte_join(ctx):
    execute(
        ctx,
        """
WITH cte_rental AS (
    SELECT staff_id,
        COUNT(rental_id) rental_count
    FROM   rental
    GROUP  BY staff_id
)
SELECT s.staff_id,
    first_name,
    last_name,
    rental_count
FROM staff s
    INNER JOIN cte_rental USING (staff_id);
        """)
