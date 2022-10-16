""" MMS crawler """
import logging
from datetime import datetime
from time import timezone
from zoneinfo import ZoneInfo

from opennem.controllers.nem import ControllerReturn, store_aemo_tableset
from opennem.core.crawlers.history import CrawlHistoryEntry, get_crawler_missing_intervals, set_crawler_history
from opennem.core.crawlers.schema import CrawlerDefinition, CrawlerPriority, CrawlerSchedule
from opennem.core.parsers.aemo.filenames import AEMODataBucketSize
from opennem.core.parsers.aemo.mms import parse_aemo_url
from opennem.core.parsers.aemo.nemweb import parse_aemo_url_optimized, parse_aemo_url_optimized_bulk
from opennem.core.parsers.dirlisting import DirlistingEntry, get_dirlisting
from opennem.core.time import get_interval, get_interval_by_size
from opennem.crawl import run_crawl
from opennem.crawlers.nemweb import run_nemweb_aemo_crawl
from opennem.schema.network import NetworkAEMORooftop, NetworkNEM
from opennem.schema.time import TimeInterval
from opennem.utils.dates import get_last_complete_day_for_network, month_series

logger = logging.getLogger("opennem.crawler.nemweb")

MMS_ARCHIVE_URL_FORMAT = "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/{year}/MMSDM_{year}_{month:02}/MMSDM_Historical_Data_SQLLoader/DATA/"

MMS_START = datetime.fromisoformat("2009-07-01T00:00:00+10:00")


class AEMOCrawlerMMSException(Exception):
    """MMS crawler exception"""

    pass


def get_mms_archive_url(year: int, month: int) -> str:
    """Get the MMS archive URL"""
    return MMS_ARCHIVE_URL_FORMAT.format(year=year, month=month)


def run_aemo_mms_crawl(
    crawler: CrawlerDefinition,
    run_fill: bool = True,
    last_crawled: bool = True,
    limit: bool = False,
    latest: bool = True,
) -> ControllerReturn | None:
    """Run the MMS crawl"""

    crawler_return: ControllerReturn | None = None

    for mms_crawl_date in month_series(
        start=MMS_START,
        end=get_last_complete_day_for_network(NetworkNEM),
    ):
        crawler.url = get_mms_archive_url(mms_crawl_date.year, mms_crawl_date.month)
        cr = process_mms_url(crawler)

        if not crawler_return:
            crawler_return = cr
        else:
            crawler_return.inserted_records += cr.inserted_records

    return crawler_return


def process_mms_url(crawler: CrawlerDefinition) -> ControllerReturn | None:
    logger.info(f"Crawling url: {crawler.url}")

    """Runs the AEMO MMS crawlers"""
    if not crawler.url and not crawler.urls:
        raise AEMOCrawlerMMSException("Require a URL to run AEMO MMS crawlers")

    try:
        dirlisting = get_dirlisting(crawler.url, timezone="Australia/Brisbane")
    except Exception as e:
        logger.error(f"Could not fetch directory listing: {crawler.url}. {e}")
        return None

    if crawler.filename_filter:
        dirlisting.apply_filter(crawler.filename_filter)

    logger.debug(
        f"Got {dirlisting.count} entries, {dirlisting.file_count} files and {dirlisting.directory_count} directories"
    )

    entries_to_fetch: list[DirlistingEntry] = dirlisting.get_files()

    if not entries_to_fetch:
        logger.error("No entries to fetch")
        return None

    for entry in entries_to_fetch:
        try:
            # @NOTE optimization - if we're dealing with a large file unzip
            # to disk and parse rather than in-memory. 100,000kb
            if crawler.bulk_insert:
                controller_returns = parse_aemo_url_optimized_bulk(entry.link, persist_to_db=True)
            elif entry.file_size and entry.file_size > 100_000:
                controller_returns = parse_aemo_url_optimized(entry.link)
            else:
                ts = parse_aemo_url(entry.link)
                controller_returns = store_aemo_tableset(ts)

            max_date = max(i.modified_date for i in entries_to_fetch if i.modified_date)

            if not controller_returns.last_modified or max_date > controller_returns.last_modified:
                controller_returns.last_modified = max_date

            if entry.aemo_interval_date:
                ch = CrawlHistoryEntry(interval=entry.aemo_interval_date, records=controller_returns.processed_records)
                set_crawler_history(crawler_name=crawler.name, histories=[ch])

        except Exception as e:
            logger.error(f"Processing error: {e}")

    return controller_returns


AEMOMMSDispatchInterconnector = CrawlerDefinition(
    priority=CrawlerPriority.high,
    schedule=CrawlerSchedule.live,
    name="au.mms.interconnector_res",
    filename_filter=".*_DISPATCHINTERCONNECTORRES_.*",
    network=NetworkNEM,
    bucket_size=AEMODataBucketSize.month,
    processor=run_aemo_mms_crawl,
)


if __name__ == "__main__":
    run_crawl(AEMOMMSDispatchInterconnector)