""" Crawl commands cli """
import logging

import click
from rich.table import Table

from opennem import console
from opennem.core.crawlers.crawler import crawlers_flush_metadata, crawlers_get_crawl_metadata
from opennem.crawl import get_crawl_set, run_crawl
from opennem.utils.timesince import timesince

logger = logging.getLogger("opennem.cli")

crawler_set = get_crawl_set()


@click.group()
def cmd_crawl_cli() -> None:
    pass


@click.command()
@click.argument("name")
@click.option("--latest", default=False, help="Run only server latest")
def crawl_cli_run(name: str, latest: bool = False) -> None:
    console.log("Run crawlers matching: {}".format(name))

    crawlers = get_crawl_set()

    try:
        crawlers_filtered = crawlers.get_crawlers_by_match(name)
    except Exception as e:
        console.log("[red]Could not find crawlers for {}[/red]: {}".format(name, e))
        return None

    if not crawlers_filtered:
        console.log("No crawlers found matchin [red]{}[/red]".format(name))
        return None

    console.log("[green]Running {} crawlers[/green]".format(len(crawlers_filtered)))

    for c in crawlers_filtered:
        console.log(
            "Running crawler {} (Version: {})\n\tlast_crawled: {}\n\tlast_processed: {}\n\tserver_latest: {}".format(
                c.name, c.version, c.last_crawled, c.last_processed, c.server_latest
            )
        )
        run_crawl(c, last_crawled=latest)


@click.command()
@click.option("--days", default=None, help="Only flush days")
@click.option("--crawler", default=None, help="Crawler name to flush")
def crawl_cli_flush(days: int | None = None, crawler: str | None = None) -> None:
    console.log("[blue]Flushing crawlers[/blue]")
    crawlers_flush_metadata(days=days, crawler_name=crawler)


@click.command()
def crawl_cli_list() -> None:
    console.log("[blue]Listing crawlers[/blue]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Crawler")
    table.add_column("Version")
    table.add_column("Last Crawled")
    table.add_column("Last Processed")
    table.add_column("Server Latest")

    crawler_meta = crawlers_get_crawl_metadata()

    for c in crawler_meta:
        table.add_row(
            c.name,
            str(c.version),
            "{} ({})".format(c.last_crawled, timesince(c.last_crawled)),
            "{} ({})".format(c.last_processed, timesince(c.last_processed)),
            "{} ({})".format(c.server_latest, timesince(c.server_latest)),
        )

    console.print(table)


cmd_crawl_cli.add_command(crawl_cli_run, name="run")
cmd_crawl_cli.add_command(crawl_cli_list, name="list")
cmd_crawl_cli.add_command(crawl_cli_flush, name="flush")
