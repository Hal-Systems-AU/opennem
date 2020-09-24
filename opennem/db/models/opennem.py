"""
    OpenNEM primary schema adapted to support multiple energy sources

    Currently supported:

    - NEM
    - WEM
"""

from decimal import Decimal
from typing import Optional

from dictalchemy import DictableModel
from geoalchemy2 import Geometry
from shapely import wkb
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    Sequence,
    Text,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from opennem.core.dispatch_type import DispatchType
from opennem.core.oid import get_ocode, get_oid

Base = declarative_base(cls=DictableModel)
metadata = Base.metadata


class BaseModel(object):
    """
        Base model for both NEM and WEM

    """

    created_by = Column(Text, nullable=True)
    # updated_by = Column(Text, nullable=True)
    # processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FuelTech(Base, BaseModel):
    __tablename__ = "fueltech"

    code = Column(Text, primary_key=True)
    label = Column(Text, nullable=True)
    renewable = Column(Boolean, default=False)

    facilities = relationship("Facility")


class Network(Base, BaseModel):
    __tablename__ = "network"

    code = Column(Text, primary_key=True)
    country = Column(Text, nullable=False)
    label = Column(Text, nullable=True)
    timezone = Column(Text, nullable=False)
    interval_size = Column(Integer, nullable=False)


class FacilityStatus(Base, BaseModel):
    __tablename__ = "facility_status"

    code = Column(Text, primary_key=True)
    label = Column(Text)


class Participant(Base, BaseModel):
    __tablename__ = "participant"

    id = Column(
        Integer,
        Sequence("seq_participant_id", start=1000, increment=1),
        primary_key=True,
    )

    code = Column(Text, unique=True, index=True)
    name = Column(Text)
    network_name = Column(Text)
    network_code = Column(Text)
    country = Column(Text)
    abn = Column(Text)

    approved = Column(Boolean, default=False)
    approved_by = Column(Text)
    approved_at = Column(DateTime(timezone=True), nullable=True)


class Location(Base):
    __tablename__ = "location"

    id = Column(
        Integer, Sequence("seq_location_id", start=1000), primary_key=True
    )

    # station_id = Column(Integer, ForeignKey("station.id"))

    address1 = Column(Text)
    address2 = Column(Text)
    locality = Column(Text)
    state = Column(Text)
    postcode = Column(Text, nullable=True)

    revisions = relationship("Revision", lazy="joined")

    # Geo fields
    place_id = Column(Text, nullable=True, index=True)
    geocode_approved = Column(Boolean, default=False)
    geocode_skip = Column(Boolean, default=False)
    geocode_processed_at = Column(DateTime, nullable=True)
    geocode_by = Column(Text, nullable=True)
    geom = Column(Geometry("POINT", srid=4326))
    boundary = Column(Geometry("MULTIPOLYGON", srid=4326))

    @hybrid_property
    def lat(self) -> Optional[float]:
        if self.geom:
            return wkb.loads(bytes(self.geom.data)).y

        return None

    @hybrid_property
    def lng(self) -> Optional[float]:
        if self.geom:
            return wkb.loads(bytes(self.geom.data)).x

        return None


class Station(Base, BaseModel):
    __tablename__ = "station"

    # __table_args__ = (
    #     UniqueConstraint(
    #         "customer_id", "location_code", name="_customer_location_uc"
    #     ),
    # )

    def __str__(self):
        return "{} <{}>".format(self.name, self.code)

    def __repr__(self):
        return "{} {} <{}>".format(self.__class__, self.name, self.code)

    id = Column(
        Integer,
        Sequence("seq_station_id", start=1000, increment=1),
        primary_key=True,
    )

    participant_id = Column(
        Integer,
        ForeignKey("participant.id", name="fk_station_participant_id"),
        nullable=True,
    )
    participant = relationship("Participant")

    location_id = Column(
        Integer,
        ForeignKey("location.id", name="fk_station_location_id"),
        nullable=True,
    )
    location = relationship("Location", lazy="joined")

    facilities = relationship("Facility", lazy="joined")

    revisions = relationship("Revision", lazy="joined")

    code = Column(Text, index=True, nullable=True)
    name = Column(Text)

    # Original network fields
    network_code = Column(Text, index=True)
    network_name = Column(Text)

    approved = Column(Boolean, default=False)
    approved_by = Column(Text)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    @hybrid_property
    def network(self) -> Optional[Network]:
        """
            Return the network from the facility

        """
        if not self.facilities or not len(self.facilities) > 0:
            return None

        return self.facilities[0].network

    @hybrid_property
    def capacity_registered(self) -> Optional[int]:
        """
            This is the sum of registered capacities for all units for
            this station

        """
        cap_reg = None

        for fac in self.facilities:
            if (
                fac.capacity_registered
                and type(fac.capacity_registered) in [int, float, Decimal]
                and fac.status_id
                in ["operating", "committed", "commissioning"]
                and fac.dispatch_type == DispatchType.GENERATOR
                and fac.active
            ):
                if not cap_reg:
                    cap_reg = 0

                cap_reg += fac.capacity_registered

        if cap_reg:
            cap_reg = round(cap_reg, 2)

        return cap_reg

    @hybrid_property
    def capacity_aggregate(self) -> Optional[int]:
        """
            This is the sum of aggregate capacities for all units

        """
        cap_agg = None

        for fac in self.facilities:
            if (
                fac.capacity_aggregate
                and type(fac.capacity_aggregate) in [int, float, Decimal]
                and fac.status_id
                in ["operating", "committed", "commissioning"]
                and fac.dispatch_type == DispatchType.GENERATOR
                and fac.active
            ):
                if not cap_agg:
                    cap_agg = 0

                cap_agg += fac.capacity_aggregate

        if cap_agg:
            cap_agg = round(cap_agg, 2)

        return cap_agg

    @hybrid_property
    def oid(self) -> str:
        return get_oid(self)

    @hybrid_property
    def ocode(self) -> str:
        return get_ocode(self)


class Facility(Base, BaseModel):
    __tablename__ = "facility"

    def __str__(self):
        return "{} <{}>".format(self.code, self.fueltech_id)

    def __repr__(self):
        return "{} {} <{}>".format(self.__class__, self.code, self.fueltech_id)

    id = Column(
        Integer,
        Sequence("seq_facility_id", start=1000, increment=1),
        primary_key=True,
    )

    network_id = Column(
        Text,
        ForeignKey("network.code", name="fk_station_network_code"),
        nullable=False,
    )
    network = relationship("Network", lazy="joined")

    fueltech_id = Column(
        Text,
        ForeignKey("fueltech.code", name="fk_facility_fueltech_id"),
        nullable=True,
    )
    fueltech = relationship(
        "FuelTech", back_populates="facilities", lazy="joined"
    )

    status_id = Column(
        Text,
        ForeignKey("facility_status.code", name="fk_facility_status_code"),
    )
    status = relationship("FacilityStatus", lazy="joined")

    station_id = Column(
        Integer,
        ForeignKey("station.id", name="fk_station_status_code"),
        nullable=True,
    )
    station = relationship("Station", back_populates="facilities")

    revisions = relationship("Revision", lazy="joined")

    # DUID but modified by opennem as an identifier
    code = Column(Text, index=True)

    # Network details
    network_code = Column(Text, nullable=True, index=True)
    network_region = Column(Text, index=True)
    network_name = Column(Text)

    active = Column(Boolean, default=True)

    dispatch_type = Column(
        Enum(DispatchType), nullable=False, default=DispatchType.GENERATOR
    )

    # @TODO remove when ref count is 0
    capacity_registered = Column(Numeric, nullable=True)

    registered = Column(DateTime, nullable=True)
    deregistered = Column(DateTime, nullable=True)

    unit_id = Column(Integer, nullable=True)
    unit_number = Column(Integer, nullable=True)
    unit_alias = Column(Text, nullable=True)
    unit_capacity = Column(Numeric, nullable=True)
    # unit_number_max = Column(Numeric, nullable=True)

    approved = Column(Boolean, default=False)
    approved_by = Column(Text)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    @hybrid_property
    def capacity_aggregate(self) -> Optional[int]:
        """
            This is unit_no * unit_capacity and can differ from registered

        """
        num_units = 1
        cap_aggr = None

        if not self.active:
            return 0

        if self.unit_number and type(self.unit_number) is int:
            num_units = self.unit_number

        if self.unit_capacity and type(self.unit_capacity) is Decimal:
            cap_aggr = num_units * self.unit_capacity

        if type(cap_aggr) is Decimal:
            cap_aggr = round(cap_aggr, 2)

        return cap_aggr

    @hybrid_property
    def duid(self) -> str:
        return self.network_code or self.code

    @hybrid_property
    def status_label(self) -> Optional[str]:
        return self.status.label if self.status else None

    @hybrid_property
    def fueltech_label(self) -> Optional[str]:
        return self.fueltech.label if self.fueltech else None

    @hybrid_property
    def oid(self) -> str:
        return get_oid(self)

    @hybrid_property
    def ocode(self) -> str:
        return get_ocode(self)


class Revision(Base, BaseModel):

    __tablename__ = "revisions"

    id = Column(
        Integer,
        Sequence("seq_revision_id", start=1000, increment=1),
        primary_key=True,
    )

    station_id = Column(
        Integer,
        ForeignKey("station.id", name="fk_revision_station_id"),
        nullable=True,
    )
    station = relationship(
        "Station", back_populates="revisions", lazy="joined"
    )

    facility_id = Column(
        Integer,
        ForeignKey("facility.id", name="fk_revision_facility_id"),
        nullable=True,
    )
    facility = relationship(
        "Facility", back_populates="revisions", lazy="joined"
    )

    location_id = Column(
        Integer,
        ForeignKey("location.id", name="fk_revision_location_id"),
        nullable=True,
    )
    location = relationship(
        "Location", back_populates="revisions", lazy="joined"
    )

    changes = Column(JSON, nullable=True)
    previous = Column(JSON, nullable=True)

    is_update = Column(Boolean, default=False)

    approved = Column(Boolean, default=False)
    approved_by = Column(Text)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_comment = Column(Text, nullable=True)

    discarded = Column(Boolean, default=False)
    discarded_by = Column(Text)
    discarded_at = Column(DateTime(timezone=True), nullable=True)

    @hybrid_property
    def parent_id(self) -> str:
        return self.station_id or self.facility_id or self.location_id

    @hybrid_property
    def parent_type(self) -> str:
        if self.station_id:
            return "station"

        if self.facility_id:
            return "facility"

        if self.location_id:
            return "location"

        return ""

    @hybrid_property
    def station_owner_id(self) -> int:
        if self.station_id:
            return self.station_id

        if self.facility_id:
            return self.facility.station.id

        if self.location:
            return self.location.station.id

    @hybrid_property
    def station_owner_name(self) -> str:
        if self.station_id:
            return self.station.name

        if self.facility_id:
            return self.facility.station.name

        if self.location:
            return self.location.station.name

    @hybrid_property
    def station_owner_code(self) -> str:
        if self.station_id:
            return self.station.code

        if self.facility_id:
            return self.facility.station.code

        if self.location:
            return self.location.station.code


class FacilityScada(Base, BaseModel):
    """
        Facility Scada
    """

    __tablename__ = "facility_scada"

    network_id = Column(
        Text,
        ForeignKey("network.code", name="fk_balancing_summary_network_code"),
        primary_key=True,
    )
    network = relationship("Network")

    trading_interval = Column(
        DateTime(timezone=True), index=True, primary_key=True
    )

    facility_code = Column(Text, nullable=False, primary_key=True, index=True)

    generated = Column(Numeric, nullable=True)
    eoi_quantity = Column(Numeric, nullable=True)


class BalancingSummary(Base, BaseModel):

    __tablename__ = "balancing_summary"

    network_id = Column(
        Text,
        ForeignKey("network.code", name="fk_balancing_summary_network_code"),
        primary_key=True,
    )
    network = relationship("Network")

    trading_interval = Column(
        DateTime(timezone=True), index=True, primary_key=True
    )
    forecast_load = Column(Numeric, nullable=True)
    generation_scheduled = Column(Numeric, nullable=True)
    generation_non_scheduled = Column(Numeric, nullable=True)
    generation_total = Column(Numeric, nullable=True)
    price = Column(Numeric, nullable=True)
