import click


@click.group(short_help="[command group] internals")
@click.pass_context
def internals(ctx):
    """postgresql 14 internals"""
    pass