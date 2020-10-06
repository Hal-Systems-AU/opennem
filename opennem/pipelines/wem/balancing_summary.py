import csv
import logging
from datetime import datetime

from scrapy.exceptions import DropItem
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import text

from opennem.db.models.opennem import BalancingSummary
from opennem.pipelines import DatabaseStoreBase
from opennem.utils.pipelines import check_spider_pipeline

from .facility_scada import wem_timezone

logger = logging.getLogger(__name__)


class WemStoreBalancingSummary(DatabaseStoreBase):
    def parse_interval(self, date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        dt_aware = wem_timezone.localize(dt)

        return dt_aware

    @check_spider_pipeline
    def process_item(self, item, spider=None):

        s = self.session()

        csvreader = csv.DictReader(item["content"].split("\n"))

        records_to_store = []

        for record in csvreader:
            trading_interval = self.parse_interval(record["Trading Interval"])

            if not trading_interval:
                continue

            records_to_store.append(
                {
                    "network_id": "WEM",
                    "trading_interval": trading_interval,
                    "forecast_load": record["Load Forecast (MW)"],
                    "generation_scheduled": record[
                        "Scheduled Generation (MW)"
                    ],
                    "generation_non_scheduled": record[
                        "Non-Scheduled Generation (MW)"
                    ],
                    "generation_total": record["Total Generation (MW)"],
                    "price": record["Final Price ($/MWh)"],
                }
            )

        stmt = insert(BalancingSummary).values(records_to_store)
        stmt.bind = self.engine
        stmt = stmt.on_conflict_do_update(
            constraint="balancing_summary_pkey",
            set_={
                "price": stmt.excluded.price,
                "generation_total": stmt.excluded.generation_total,
            },
        )

        try:
            r = s.execute(stmt)
            s.commit()
            return r
        except Exception as e:
            logger.error("Error inserting records")
            logger.error(e)
        finally:
            s.close()

        return len(records_to_store)


class WemStoreBalancingSummaryArchive(DatabaseStoreBase):
    def parse_interval(self, date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        dt_aware = wem_timezone.localize(dt)

        return dt_aware

    @check_spider_pipeline
    def process_item(self, item, spider=None):

        s = self.session()

        csvreader = csv.DictReader(item["content"].split("\n"))

        objects = [
            BalancingSummary(
                network_id="WEM",
                trading_interval=self.parse_interval(row["Trading Interval"]),
                forecast_load=row["Load Forecast (MW)"],
                generation_scheduled=row["Scheduled Generation (MW)"],
                generation_non_scheduled=row["Non-Scheduled Generation (MW)"],
                generation_total=row["Total Generation (MW)"],
                price=row["Final Price ($/MWh)"],
            )
            for row in csvreader
        ]

        try:
            s.bulk_save_objects(objects)
            s.commit()
        except Exception as e:
            logger.error("Error: {}".format(e))
            raise e
        finally:
            s.close()

        return len(objects)
