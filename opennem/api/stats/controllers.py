import logging
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from textwrap import dedent
from typing import Any, Dict, List, Optional, Union

import pytz
from datetime_truncate import truncate as date_trunc
from fastapi.exceptions import HTTPException
from starlette import status

from opennem.api.time import human_to_interval
from opennem.db import get_database_engine
from opennem.schema.network import NetworkSchema
from opennem.schema.time import TimeInterval, TimePeriod
from opennem.schema.units import UnitDefinition
from opennem.utils.cache import cache_scada_result
from opennem.utils.numbers import cast_trailing_nulls, trim_nulls
from opennem.utils.sql import duid_in_case
from opennem.utils.timezone import is_aware, make_aware
from opennem.utils.version import get_version

from .schema import (
    DataQueryResult,
    OpennemData,
    OpennemDataHistory,
    OpennemDataSet,
    ScadaDateRange,
)

logger = logging.getLogger(__name__)


def stats_factory(
    stats: List[DataQueryResult],
    units: UnitDefinition,
    interval: TimeInterval,
    period: Optional[TimePeriod] = None,
    network: Optional[NetworkSchema] = None,
    timezone: Optional[Union[timezone, str]] = None,
    code: Optional[str] = None,
    region: Optional[str] = None,
    include_group_code: bool = False,
    fueltech_group: Optional[bool] = False,
    group_field: Optional[str] = None,
    data_id: Optional[str] = None,
    localize: Optional[bool] = True,
    include_code: Optional[bool] = True,
    cast_nulls: Optional[bool] = True,
) -> Optional[OpennemDataSet]:
    """
    Takes a list of data query results and returns OpennemDataSets

    @TODO optional groupby field
    @TODO multiple groupings / slight refactor

    """

    if network:
        timezone = network.get_timezone()

    group_codes = list(set([i.group_by for i in stats if i.group_by]))

    stats_grouped = []

    for group_code in group_codes:

        data_grouped: Dict[datetime, Any] = dict()

        for stat in stats:
            if stat.group_by != group_code:
                continue

            if stat.interval not in data_grouped:
                data_grouped[stat.interval] = None

            # if stat.result:
            data_grouped[stat.interval] = stat.result

        data_sorted = OrderedDict(sorted(data_grouped.items()))

        data_value = list(data_sorted.values())

        # Skip null series
        if len([i for i in data_value if i]) == 0:
            continue

        # @TODO possible bring this back
        # Skip zero series
        # if sum([i for i in data_value if i]) == 0:
        # continue

        # Cast trailing nulls
        if (not units.name.startswith("temperature") or (units.cast_nulls is True)) and (
            cast_nulls is True
        ):
            data_value = cast_trailing_nulls(data_value)

        data_trimmed = dict(zip(data_sorted.keys(), data_value))

        data_trimmed = trim_nulls(data_trimmed)

        # Find start/end dates
        dates = list(data_trimmed.keys())

        if not dates:
            return None

        start = min(dates)
        end = max(dates)

        # should probably make sure these are the same TZ
        if localize:
            if timezone and not is_aware(start):
                start = make_aware(start, timezone)

            if timezone and not is_aware(end):
                end = make_aware(end, timezone)

            if timezone and localize and network and network.offset:
                tz = pytz.FixedOffset(int(network.offset))

                start = start.astimezone(tz)
                end = end.astimezone(tz)

        # Everything needs a timezone even flat dates
        if network and timezone and not is_aware(start):
            start = start.replace(tzinfo=network.get_fixed_offset())

        if network and timezone and not is_aware(end):
            end = end.replace(tzinfo=network.get_fixed_offset())

        # @TODO compose this and make it generic - some intervals
        # get truncated.
        # trunc the date for days and months
        if interval == human_to_interval("1d"):
            start = date_trunc(start, truncate_to="day")
            end = date_trunc(end, truncate_to="day")

        if interval == human_to_interval("1M"):
            start = date_trunc(start, truncate_to="month")
            end = date_trunc(end, truncate_to="month")

        # free
        dates = []

        history = OpennemDataHistory(
            start=start,
            last=end,
            interval=interval.interval_human,
            data=data_trimmed.values(),
        )

        data = OpennemData(
            data_type=units.unit_type,
            units=units.unit,
            # interval=interval,
            # period=period,
            history=history,
        )

        if include_code:
            data.code = group_code

        if network:
            data.network = network.code.lower()

        # *sigh* - not the most flexible model
        # @TODO fix this schema and make it more flexible
        if fueltech_group:
            data.fuel_tech = group_code

            data_comps = [
                # @NOTE disable for now since FE doesn't
                # support it
                network.country if network else None,
                network.code.lower() if network else None,
                region.lower() if region and region.lower() != network.code.lower() else None,
                "fuel_tech",
                group_code,
                units.unit_type,
            ]

            data.id = ".".join(i for i in data_comps if i)
            # @TODO make this an alias
            data.type = units.unit_type

        if group_field:
            group_fields = []

            # setattr(data, group_field, group_code)

            if network:
                group_fields.append(network.country.lower())
                group_fields.append(network.code.lower())

            if region:
                if region.lower() != network.code.lower():
                    group_fields.append(region.lower())

            if units.name_alias:
                group_fields.append(units.name_alias)

            elif units.unit_type:
                group_fields.append(units.unit_type)

            if group_code and include_group_code:
                group_fields.append(group_code)
                group_fields.append(group_field)

            data.id = ".".join([f for f in group_fields if f])
            data.type = units.unit_type

        if data_id:
            data.id = data_id

        if not data.id:
            _id_list = []

            # @NOTE disable for now since FE doesn't
            # support it
            # network.country if network else None,

            if network:
                _id_list.append(network.code.lower())

            if region and (region.lower() != network.code.lower()):
                _id_list.append(region.lower())

            if group_code:
                _id_list.append(group_code.lower())

            if units and units.name_alias:
                _id_list.append(units.name_alias)
            elif units and units.name:
                _id_list.append(units.name)

            data.id = ".".join([f for f in _id_list if f])
            data.type = units.unit_type

        if region:
            data.region = region

        stats_grouped.append(data)

    dt_now = datetime.now()

    if network:
        dt_now = dt_now.astimezone(network.get_timezone())

    # @NOTE this should probably be
    # country.network.region
    if not code:
        if network:
            code = network.code

        if region:
            code = region

    stat_set = OpennemDataSet(
        type=units.unit_type,
        data=stats_grouped,
        created_at=dt_now,
        version=get_version(),
    )

    if include_code:
        stat_set.code = code

    if network:
        stat_set.network = network.code

    if region:
        stat_set.region = region

    return stat_set


def networks_to_in(networks: List[NetworkSchema]) -> str:
    codes = ["'{}'".format(n.code) for n in networks]

    return ", ".join(codes)


@cache_scada_result
def get_scada_range(
    network: Optional[NetworkSchema] = None,
    networks: Optional[List[NetworkSchema]] = None,
    network_region: Optional[str] = None,
    facilities: Optional[List[str]] = None,
    energy: bool = False,
) -> Optional[ScadaDateRange]:
    """Get the start and end dates for a network query. This is more efficient
    than providing or querying the range at query time
    """
    engine = get_database_engine()

    __query = """
    select
        min(f.data_first_seen) at time zone '{timezone}',
        max(fs.trading_interval)  at time zone '{timezone}'
    from facility_scada fs
    left join facility f on fs.facility_code = f.code
    where
        fs.trading_interval >= '{date_min}' and
        {facility_query}
        {network_query}
        {network_region_query}
        f.fueltech_id not in ('solar_rooftop', 'imports', 'exports')
        and f.interconnector is FALSE
        and fs.{field} is not null;
    """

    network_query = ""
    timezone = network.timezone_database if network else "UTC"
    field_name = "generated"

    if network and network.code in ["WEM"]:
        energy = True

    if energy is True:
        field_name = "eoi_quantity"

    # Only look back 7 days because the query is more optimized
    date_min = datetime.now() - timedelta(days=7)

    if network:
        network_query = f"f.network_id = '{network.code}' and"

    if networks:
        net_case = networks_to_in(networks)
        network_query = "f.network_id IN ({}) and ".format(net_case)

    network_region_query = ""

    if network_region:
        network_region_query = f"f.network_region = '{network_region.code}' and"

    facility_query = ""

    if facilities:
        fac_case = duid_in_case(facilities)
        facility_query = "f.code IN ({}) and ".format(fac_case)

    scada_range_query = dedent(
        __query.format(
            field=field_name,
            date_min=date_min,
            facility_query=facility_query,
            network_query=network_query,
            network_region_query=network_region_query,
            timezone=timezone,
        )
    )

    with engine.connect() as c:
        logger.debug(scada_range_query)
        scada_range_result = list(c.execute(scada_range_query))

        if len(scada_range_result) < 1:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No results",
            )

        scada_min = scada_range_result[0][0]
        scada_max = scada_range_result[0][1]

    if not scada_min or not scada_max:
        return None

    scada_range = ScadaDateRange(start=scada_min, end=scada_max, network=network)

    return scada_range
