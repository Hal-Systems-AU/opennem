from datetime import timezone as timezone_native
from datetime import tzinfo
from typing import Any, List, Optional, Union

import pytz
from pydantic import Field
from pytz import timezone as pytz_timezone

from opennem.core.time import get_interval_by_size
from opennem.schema.time import TimeInterval
from opennem.utils.timezone import get_current_timezone

from .core import BaseConfig


class NetworkNetworkRegion(BaseConfig):
    code: str


class NetworkRegionSchema(BaseConfig):
    network_id: str
    code: str
    timezone: Optional[str]


class NetworkSchema(BaseConfig):
    code: str
    country: str
    label: str

    regions: Optional[List[NetworkNetworkRegion]]
    timezone: str = Field(..., description="Network timezone")
    timezone_database: str = Field("UTC", description="Database timezone format")
    offset: Optional[int] = Field(None, description="Network time offset in minutes")

    interval_size: int = Field(..., description="Size of network interval in minutes")

    interval_shift: int = Field(0, description="Size of reading shift in minutes")

    def get_interval(self) -> Optional[TimeInterval]:
        if not self.interval_size:
            return None

        interval = get_interval_by_size(self.interval_size)

        return interval

    def get_timezone(
        self, postgres_format: bool = False
    ) -> Union[timezone_native, pytz_timezone, str]:
        """Get the network timezone

        @TODO define crawl timezones vs network timezone
        """

        # If a fixed offset is defined for the network use that
        if self.offset:
            tz = pytz.FixedOffset(self.offset)

        # If the network alternatively defines a timezone
        if not tz and self.timezone:
            tz = pytz_timezone(self.timezone)

        # Default to current system timezone
        if not tz:
            tz = get_current_timezone()

        if postgres_format:
            tz = str(tz)[:3]

        return tz

    def get_crawl_timezone(self) -> Any:
        tz = pytz_timezone(self.timezone)

        return tz

    def get_fixed_offset(self) -> Union[Any, tzinfo]:
        if self.offset:
            return pytz.FixedOffset(self.offset)

        raise Exception("No offset set")

    @property
    def intervals_per_hour(self) -> float:
        return 60 / self.interval_size


class NetworkRegion(BaseConfig):
    code: str
    network: NetworkSchema

    timezone: Optional[str] = Field(None, description="Network timezone")
    timezone_database: Optional[str] = Field("UTC", description="Database timezone format")
    offset: Optional[int] = Field(None, description="Network time offset in minutes")


# @TODO move this to db + fixture

NetworkNEM = NetworkSchema(
    code="NEM",
    label="NEM",
    country="au",
    timezone="Australia/Brisbane",
    timezone_database="AEST",
    offset=600,
    interval_size=5,
    interval_shift=5,
)

NetworkWEM = NetworkSchema(
    code="WEM",
    label="WEM",
    country="au",
    timezone="Australia/Perth",
    timezone_database="AWST",
    offset=480,
    interval_size=30,
)

NetworkAPVI = NetworkSchema(
    code="APVI",
    label="APVI",
    country="au",
    timezone="Australia/Sydney",
    timezone_database="AEST",
    offset=600,
    interval_size=15,
)

# This is a "virtual" network that is made up of
# NEM + WEM
NetworkAU = NetworkSchema(
    code="AU",
    label="AU",
    country="au",
    timezone="Australia/Sydney",
    timezone_database="AEST",
    offset=600,
    interval_size=30,
)


NetworkAEMORooftop = NetworkSchema(
    code="AEMO_ROOFTOP",
    label="AEMO Rooftop",
    country="au",
    timezone="Australia/Sydney",
    timezone_database="AEST",
    offset=600,
    interval_size=30,
)

NETWORKS = [NetworkNEM, NetworkWEM, NetworkAPVI, NetworkAU]
