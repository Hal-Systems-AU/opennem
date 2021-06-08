"""
    Generates the map of queries and paths to export to S3 buckets
    for opennem.org.au

"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from opennem.api.stats.controllers import ScadaDateRange, get_scada_range
from opennem.api.time import human_to_interval, human_to_period
from opennem.core.network_region_bom_station_map import get_network_region_weather_station
from opennem.core.networks import (
    NetworkAPVI,
    NetworkAU,
    NetworkNEM,
    NetworkSchema,
    NetworkWEM,
    network_from_network_code,
)
from opennem.db import SessionLocal
from opennem.db.models.opennem import Network
from opennem.schema.network import NetworkAEMORooftop, NetworkAEMORooftopBackfill
from opennem.schema.time import TimeInterval, TimePeriod
from opennem.utils.dates import week_series
from opennem.utils.version import VersionPart, get_version

logger = logging.getLogger(__name__)

VERSION_MAJOR = get_version(version_part=VersionPart.MAJOR)
STATS_FOLDER = "stats"


class StatType(Enum):
    power = "power"
    energy = "energy"
    interchange = "interchange"
    gov = "gov"


class PriorityType(Enum):
    live = 1
    daily = 2
    monthly = 3
    history = 4


def date_range_from_week(
    year: int, week: int, network: Optional[NetworkSchema] = None
) -> ScadaDateRange:
    """
    Get a scada date range from week number with
    network awareness
    """
    start_date_str = f"{year}-W{week - 1}-1"
    start_date_dt = datetime.strptime(start_date_str, "%Y-W%W-%w")

    end_date = start_date_dt + timedelta(days=7)

    scada_range = ScadaDateRange(start=start_date_dt, end=end_date, network=network)

    return scada_range


def priority_from_name(priority_name: str) -> PriorityType:
    """Get the PriorityType enum def from a priority string name"""
    priority_names = [i.name for i in PriorityType]

    if priority_name not in priority_names:
        raise Exception("Could not find priority: {}".format(priority_name))

    return PriorityType[priority_name]


class StatExport(BaseModel):
    """Defines an export map - a set of variables that produces a JSON export"""

    stat_type: StatType = StatType.energy
    priority: PriorityType = PriorityType.live
    country: str
    network: NetworkSchema
    networks: Optional[List[NetworkSchema]]
    network_region: Optional[str]
    network_region_query: Optional[str]
    date_range: Optional[ScadaDateRange]
    bom_station: Optional[str]
    year: Optional[int]
    week: Optional[int]
    period: Optional[TimePeriod]
    interval: TimeInterval
    file_path: Optional[str]

    @property
    def path(self) -> str:
        _path_components = [
            f"v{VERSION_MAJOR}",
            STATS_FOLDER,
            self.country,
            self.network.code,
        ]

        if self.network_region:
            _path_components.append(self.network_region)

        _path_components.append(self.stat_type.value)

        # only show the period when it's not explicitly a year
        if self.period and not self.year:
            _path_components.append(self.period.period_human)

        if self.week:
            _path_components.append("week")

        if self.year:
            _path_components.append(str(self.year))

        if self.week:
            _path_components.append(str(self.week))

        dir_path = "/".join([str(i) for i in _path_components])

        return "{}.json".format(dir_path)


class StatMetadata(BaseModel):
    """Defines a set of export maps with methods to filter"""

    date_created: datetime
    version: Optional[str]
    resources: List[StatExport]

    def get_by_stat_type(self, stat_type: StatType) -> StatMetadata:
        em = self.copy()
        em.resources = list(filter(lambda s: s.stat_type == stat_type, self.resources))
        return em

    def get_by_network_id(
        self,
        network_id: str,
    ) -> StatMetadata:
        em = self.copy()
        em.resources = list(filter(lambda s: s.network.code == network_id, self.resources))
        return em

    def get_by_network_region(
        self,
        network_region: str,
    ) -> StatMetadata:
        em = self.copy()
        em.resources = list(filter(lambda s: s.network_region == network_region, self.resources))
        return em

    def get_by_year(
        self,
        year: int,
    ) -> StatMetadata:
        em = self.copy()
        em.resources = list(filter(lambda s: s.year == year, self.resources))
        return em

    def get_by_years(
        self,
        years: List[int],
    ) -> StatMetadata:
        em = self.copy()
        em.resources = list(filter(lambda s: s.year in years, self.resources))
        return em

    def get_by_priority(self, priority: PriorityType) -> StatMetadata:
        em = self.copy()
        em.resources = list(
            filter(
                lambda s: s.priority == priority,
                self.resources,
            )
        )
        return em


def get_export_map() -> StatMetadata:
    """
    Generates a map of all export JSONs

    """
    session = SessionLocal()

    networks = session.query(Network).filter(Network.export_set.is_(True)).all()

    if not networks:
        raise Exception("No networks")

    countries = list(set([network.country for network in networks]))

    _exmap = []

    for country in countries:
        # @TODO derive this
        scada_range = get_scada_range(network=NetworkAU, networks=[NetworkNEM, NetworkWEM])

        if not scada_range:
            raise Exception("Require a scada range for NetworkAU")

        export = StatExport(
            stat_type=StatType.power,
            priority=PriorityType.live,
            country=country,
            date_range=scada_range,
            network=NetworkAU,
            networks=[
                NetworkNEM,
                NetworkWEM,
                NetworkAEMORooftop,
                NetworkAEMORooftopBackfill,
                NetworkAPVI,
            ],
            interval=NetworkAU.get_interval(),
            period=human_to_period("7d"),
        )

        _exmap.append(export)

        for year, week in week_series(scada_range.end, scada_range.start):
            export = StatExport(
                stat_type=StatType.power,
                priority=PriorityType.history,
                country=country,
                network=NetworkAU,
                networks=[NetworkNEM, NetworkWEM],
                year=year,
                week=week,
                date_range=date_range_from_week(year, week, NetworkAU),
            )
            _exmap.append(export)

        for year in range(
            datetime.now().year,
            scada_range.start.year - 1,
            -1,
        ):
            export = StatExport(
                stat_type=StatType.energy,
                priority=PriorityType.daily,
                country=country,
                date_range=scada_range,
                network=NetworkAU,
                networks=[
                    NetworkNEM,
                    NetworkWEM,
                    NetworkAEMORooftop,
                    NetworkAEMORooftopBackfill,
                    NetworkAPVI,
                ],
                year=year,
                interval=human_to_interval("1d"),
                period=human_to_period("1Y"),
            )
            _exmap.append(export)

        export = StatExport(
            stat_type=StatType.energy,
            priority=PriorityType.monthly,
            country=country,
            date_range=scada_range,
            network=NetworkAU,
            networks=[
                NetworkNEM,
                NetworkWEM,
                NetworkAEMORooftop,
                NetworkAEMORooftopBackfill,
                NetworkAPVI,
            ],
            interval=human_to_interval("1M"),
            period=human_to_period("all"),
        )
        _exmap.append(export)

    for network in networks:
        network_schema = network_from_network_code(network.code)
        scada_range = get_scada_range(network=network_schema)
        bom_station = get_network_region_weather_station(network.code)

        export = StatExport(
            stat_type=StatType.power,
            priority=PriorityType.live,
            country=network.country,
            date_range=scada_range,
            network=network_schema,
            bom_station=bom_station,
            interval=network_schema.get_interval(),
            period=human_to_period("7d"),
        )

        if network.code == "WEM":
            export.networks = [NetworkWEM, NetworkAPVI]
            export.network_region_query = "WEM"

        if network.code == "NEM":
            export.networks = [NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill]

        _exmap.append(export)

        if not scada_range:
            raise Exception("Require a scada range for network: {}".format(network.code))

        for year, week in week_series(scada_range.end, scada_range.start):
            export = StatExport(
                stat_type=StatType.power,
                priority=PriorityType.history,
                country=network.country,
                network=network_schema,
                year=year,
                week=week,
                date_range=date_range_from_week(year, week, NetworkAU),
            )

            if network.code == "WEM":
                export.networks = [NetworkWEM, NetworkAPVI]
                export.network_region_query = "WEM"

            _exmap.append(export)

        for year in range(
            datetime.now().year,
            scada_range.start.year - 1,
            -1,
        ):
            export = StatExport(
                stat_type=StatType.energy,
                priority=PriorityType.daily,
                country=network.country,
                date_range=scada_range,
                network=network_schema,
                bom_station=bom_station,
                year=year,
                period=human_to_period("1Y"),
                interval=human_to_interval("1d"),
            )

            if network.code == "WEM":
                export.networks = [NetworkWEM, NetworkAPVI]
                export.network_region_query = "WEM"

            if network.code == "NEM":
                export.networks = [NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill]

            _exmap.append(export)

        export = StatExport(
            stat_type=StatType.energy,
            priority=PriorityType.monthly,
            country=network.country,
            date_range=scada_range,
            network=network_schema,
            bom_station=bom_station,
            interval=human_to_interval("1M"),
            period=human_to_period("all"),
        )

        if network.code == "WEM":
            export.networks = [NetworkWEM, NetworkAPVI]
            export.network_region_query = "WEM"

        if network.code == "NEM":
            export.networks = [NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill]

        _exmap.append(export)

        # Skip cases like wem/wem where region is supurfelous
        if len(network.regions) < 2:
            continue

        for region in network.regions:
            scada_range = get_scada_range(network=network_schema, network_region=region)
            bom_station = get_network_region_weather_station(region.code)

            if not scada_range:
                raise Exception(
                    "Require a scada range for network {} and region {}".format(
                        network_schema.code, region
                    )
                )

            export = StatExport(
                stat_type=StatType.power,
                priority=PriorityType.live,
                country=network.country,
                date_range=scada_range,
                network=network_schema,
                network_region=region.code,
                bom_station=bom_station,
                period=human_to_period("7d"),
                interval=network_schema.get_interval(),
            )

            if network.code == "WEM":
                export.networks = [NetworkWEM, NetworkAPVI]
                export.network_region_query = "WEM"

            if network.code == "NEM":
                export.networks = [NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill]

            _exmap.append(export)

            for year in range(
                datetime.now().year,
                scada_range.start.year - 1,
                -1,
            ):
                export = StatExport(
                    stat_type=StatType.energy,
                    priority=PriorityType.daily,
                    country=network.country,
                    date_range=scada_range,
                    network=network_schema,
                    network_region=region.code,
                    networks=[NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill],
                    bom_station=bom_station,
                    year=year,
                    period=human_to_period("1Y"),
                    interval=human_to_interval("1d"),
                )
                _exmap.append(export)

            export = StatExport(
                stat_type=StatType.energy,
                priority=PriorityType.monthly,
                country=network.country,
                date_range=scada_range,
                network=network_schema,
                networks=[NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill],
                network_region=region.code,
                bom_station=bom_station,
                period=human_to_period("all"),
                interval=human_to_interval("1M"),
            )

            if network.code == "WEM":
                export.networks = [NetworkWEM, NetworkAPVI]
                export.network_region_query = "WEM"

            if network.code == "NEM":
                export.networks = [NetworkNEM, NetworkAEMORooftop, NetworkAEMORooftopBackfill]

            _exmap.append(export)

    export_meta = StatMetadata(
        date_created=datetime.now(), version=get_version(), resources=_exmap
    )

    return export_meta


if __name__ == "__main__":
    pass
