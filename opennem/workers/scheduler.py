# pylint: disable=no-name-in-module
# pylint: disable=no-self-argument
# pylint: disable=no-member
"""
Primary scheduler runs:

 * website json export tasks
 * refreshing materialized views
 * monitoring tasks

"""
import logging
import platform

from huey import PriorityRedisHuey, crontab

from opennem.api.export.map import PriorityType, refresh_export_map, refresh_weekly_export_map
from opennem.api.export.tasks import (
    export_all_daily,
    export_all_monthly,
    export_electricitymap,
    export_flows,
    export_metadata,
    export_power,
)
from opennem.crawl import run_crawl
from opennem.crawlers.apvi import APVIRooftopTodayCrawler
from opennem.crawlers.bom import BOMCapitals
from opennem.crawlers.nemweb import (
    AEMONEMDispatchActualGEN,
    AEMONEMNextDayDispatch,
    AEMONemwebDispatchIS,
    AEMONemwebRooftop,
    AEMONemwebRooftopForecast,
    AEMONemwebTradingIS,
    AEMONNemwebDispatchScada,
)
from opennem.crawlers.wem import WEMBalancing, WEMBalancingLive, WEMFacilityScada, WEMFacilityScadaLive
from opennem.exporter.geojson import export_facility_geojson
from opennem.exporter.historic import export_historic_intervals
from opennem.monitors.emissions import alert_missing_emission_factors
from opennem.monitors.facility_seen import facility_first_seen_check
from opennem.monitors.opennem import check_opennem_interval_delays
from opennem.notifications.slack import slack_message
from opennem.settings import IS_DEV, settings  # noqa: F401
from opennem.workers.backup import run_backup
from opennem.workers.daily import daily_runner
from opennem.workers.daily_summary import run_daily_fueltech_summary
from opennem.workers.emissions import run_emission_update_day
from opennem.workers.facility_data_ranges import update_facility_seen_range
from opennem.workers.network_data_range import run_network_data_range_update
from opennem.workers.system import clean_tmp_dir

# Py 3.8 on MacOS changed the default multiprocessing model
if platform.system() == "Darwin":
    import multiprocessing

    try:
        multiprocessing.set_start_method("fork")
    except RuntimeError:
        # sometimes it has already been set by
        # other libs
        pass

redis_host = None

if settings.cache_url:
    redis_host = settings.cache_url.host

huey = PriorityRedisHuey("opennem.scheduler", host=redis_host)

logger = logging.getLogger("openenm.scheduler")

regular_schedule_minute_interval = 1
frequent_schedule_minute_interval = 5

if IS_DEV:
    regular_schedule_minute_interval = 5
    frequent_schedule_minute_interval = 5


# crawler tasks live
@huey.periodic_task(crontab(minute=f"*/{regular_schedule_minute_interval}"))
@huey.lock_task("crawler_live_nemweb_dispatch_scada")
def crawl_run_aemo_nemweb_dispatch_scada() -> None:
    dispatch_scada = run_crawl(AEMONNemwebDispatchScada)
    dispatch_is = run_crawl(AEMONemwebDispatchIS)
    trading_is = run_crawl(AEMONemwebTradingIS)
    rooftop = run_crawl(AEMONemwebRooftop)

    if not dispatch_scada or not dispatch_is or not trading_is or not rooftop:
        return None

    if (
        dispatch_scada.inserted_records
        or dispatch_is.inserted_records
        or trading_is.inserted_records
        or rooftop.inserted_records
    ):
        export_power(priority=PriorityType.live)


@huey.periodic_task(crontab(minute="*/10"))
@huey.lock_task("crawler_run_bom_capitals")
def crawler_run_bom_capitals() -> None:
    run_crawl(BOMCapitals)


# crawler tasks frequent
@huey.periodic_task(crontab(minute="*/15"))
@huey.lock_task("crawler_run_wem_balancing_live")
def crawler_run_wem_balancing_live() -> None:
    apvi = run_crawl(APVIRooftopTodayCrawler)
    wem_balancing = run_crawl(WEMBalancingLive)
    wem_scada = run_crawl(WEMFacilityScadaLive)

    if not apvi or not wem_balancing or not wem_scada:
        return None

    if apvi.inserted_records or wem_balancing.inserted_records or wem_scada.inserted_records:
        export_power(priority=PriorityType.live)


@huey.periodic_task(crontab(hour="*/1", minute="30"))
@huey.lock_task("crawler_run_wem_facility_scada")
def crawler_run_wem_facility_scada() -> None:
    wem_scada = run_crawl(WEMFacilityScada)
    wem_balancing = run_crawl(WEMBalancing)

    if not wem_scada or not wem_balancing:
        return None

    if wem_scada.inserted_records or wem_balancing.inserted_records:
        export_power(priority=PriorityType.live)


@huey.periodic_task(crontab(hour="*/6", minute="33"), retries=5, retry_delay=90)
@huey.lock_task("crawler_run_aemo_nemweb_rooftop_forecast")
def crawler_run_aemo_nemweb_rooftop_forecast() -> None:
    run_crawl(AEMONemwebRooftopForecast)


# daily tasks
# run daily morning task
@huey.periodic_task(crontab(hour="6,7", minute="15,45"), retries=3, retry_delay=120)
@huey.lock_task("db_run_energy_gapfil")
def db_run_energy_gapfil() -> None:
    dispatch_actuals = run_crawl(AEMONEMDispatchActualGEN)
    dispatch_gen = run_crawl(AEMONEMNextDayDispatch)

    if not dispatch_gen or not dispatch_actuals:
        return None

    if dispatch_actuals.inserted_records or dispatch_gen.inserted_records:
        daily_runner(days=2)


# export tasks
@huey.periodic_task(crontab(minute="*/15"), priority=90)
@huey.lock_task("schedule_custom_tasks")
def schedule_custom_tasks() -> None:
    if settings.workers_run:
        export_electricitymap()
        export_flows()


@huey.periodic_task(crontab(hour="8", minute="15"), priority=50)
@huey.lock_task("schedule_export_all_daily")
def schedule_export_all_daily() -> None:
    if settings.workers_run:
        export_all_daily()
        export_all_monthly()


@huey.periodic_task(crontab(hour="12", minute="19"))
@huey.lock_task("schedule_power_weeklies")
def schedule_power_weeklies() -> None:
    """
    Run weekly power outputs
    """
    export_power(priority=PriorityType.history, latest=True)
    slack_message(f"Weekly power outputs complete on {settings.env}")


@huey.periodic_task(crontab(hour="8", minute="45"))
@huey.lock_task("run_export_latest_historic_intervals")
def run_export_latest_historic_intervals() -> None:
    """Run latest historic exports"""
    export_historic_intervals(limit=1)
    slack_message(f"Historic interval outputs complete on {settings.env}")


# geojson maps
@huey.periodic_task(crontab(minute="*/30"), priority=50)
@huey.lock_task("schedule_export_geojson")
def schedule_export_geojson() -> None:
    if settings.workers_run:
        export_facility_geojson()


# metadata
@huey.periodic_task(crontab(hour="*/12", minute="30"), priority=30)
@huey.lock_task("schedule_export_metadata")
def schedule_export_metadata() -> None:
    if settings.workers_run:
        export_metadata()


# Monitoring tasks
@huey.periodic_task(crontab(hour="10", minute="45"))
@huey.lock_task("db_run_daily_fueltech_summary")
def db_run_daily_fueltech_summary() -> None:
    run_daily_fueltech_summary()


# @huey.periodic_task(crontab(hour="18", minute="30"), retries=4, retry_delay=120)
# @huey.lock_task("db_run_aggregates_all")
# def db_run_aggregates_all() -> None:
#     run_aggregates_all()


@huey.periodic_task(crontab(hour="6", minute="45"))
@huey.lock_task("db_run_emission_tasks")
def db_run_emission_tasks() -> None:
    try:
        run_emission_update_day(days=12)
    except Exception as e:
        logger.error("Error running emission update: {}".format(str(e)))


@huey.periodic_task(crontab(minute="*/60"), priority=80)
@huey.lock_task("monitor_opennem_intervals")
def monitor_opennem_intervals() -> None:
    if settings.env != "production":
        return None

    for network_code in ["NEM", "WEM"]:
        check_opennem_interval_delays(network_code)


@huey.periodic_task(crontab(hour="8", minute="45"), priority=10)
@huey.lock_task("monitor_emission_factors")
def monitor_emission_factors() -> None:
    alert_missing_emission_factors()


# worker tasks
@huey.periodic_task(crontab(hour="10", minute="1"))
@huey.lock_task("schedule_facility_first_seen_check")
def schedule_facility_first_seen_check() -> None:
    """Check for new DUIDS"""
    if settings.env == "production":
        facility_first_seen_check()


@huey.periodic_task(crontab(hour="9", minute="45"))
@huey.lock_task("db_facility_seen_update")
def db_facility_seen_update() -> None:
    update_facility_seen_range()
    slack_message(f"Updated facility seen range on {settings.env}")


@huey.periodic_task(crontab(hour="10", minute="15"))
@huey.lock_task("run_run_network_data_range_update")
def run_run_network_data_range_update() -> None:
    run_network_data_range_update()
    slack_message("Ran network data range on {}".format(settings.env))


@huey.periodic_task(crontab(hour="1,12", minute="30"))
@huey.lock_task("run_refresh_export_maps")
def run_refresh_export_maps() -> None:
    refresh_export_map()
    refresh_weekly_export_map()


# admin tasks


@huey.periodic_task(crontab(day="1", hour="15", minute="45"))
@huey.lock_task("task_run_backup")
def task_run_backup() -> None:
    dest_file = run_backup()
    slack_message(f"Ran backup on {settings.env} to {dest_file}")


@huey.periodic_task(crontab(hour="8,16", minute="45"))
@huey.lock_task("run_clean_tmp_dir")
def run_clean_tmp_dir() -> None:
    clean_tmp_dir()
