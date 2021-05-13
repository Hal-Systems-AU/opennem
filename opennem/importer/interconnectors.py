"""
    Create stations on NEM for interconnectors
    which provide stats on region flows.


"""

import logging
from typing import List

from opennem.core.dispatch_type import DispatchType
from opennem.core.loader import load_data
from opennem.core.networks import state_from_network_region
from opennem.core.parsers.aemo import AEMOParserException, parse_aemo_csv
from opennem.db import SessionLocal
from opennem.db.models.opennem import Facility, Location, Station
from opennem.schema.aemo.mms import MarketConfigInterconnector
from opennem.utils.mime import decode_bytes

logger = logging.getLogger(__name__)

INTERCONNECTOR_TABLE = "market_config_interconnector"


def import_nem_interconnects() -> None:
    session = SessionLocal()

    # Load the MMS CSV file that contains interconnector info
    csv_data = load_data(
        "mms/PUBLIC_DVD_INTERCONNECTOR_202006010000.CSV",
        from_project=True,
    )

    # gotta be a string otherwise decode
    if not isinstance(csv_data, str):
        csv_data = decode_bytes(csv_data)

    # parse the AEMO CSV into schemas
    aemo_table_set = None

    try:
        aemo_table_set = parse_aemo_csv(csv_data)
    except AEMOParserException as e:
        logger.error(e)
        return None

    if not aemo_table_set:
        return None

    if not aemo_table_set.has_table(INTERCONNECTOR_TABLE):
        logger.error("Could not find table {}".format(INTERCONNECTOR_TABLE))
        return None

    int_table = aemo_table_set.get_table(INTERCONNECTOR_TABLE)

    if not int_table:
        logger.error("Could not fetch table: {}".format(INTERCONNECTOR_TABLE))

    records: List[MarketConfigInterconnector] = int_table.get_records()

    for interconnector in records:
        if not isinstance(interconnector, MarketConfigInterconnector):
            raise Exception("Not what we're looking for ")

        # skip SNOWY
        # @TODO do these need to be remapped for historical
        if interconnector.regionfrom in ["SNOWY1"] or interconnector.regionto in ["SNOWY1"]:
            continue

        logger.debug(interconnector)

        interconnector_station = (
            session.query(Station)
            .filter_by(code=interconnector.interconnectorid)
            .filter_by(network_code=interconnector.interconnectorid)
            .one_or_none()
        )

        if not interconnector_station:
            interconnector_station = Station(
                code=interconnector.interconnectorid,
                network_code=interconnector.interconnectorid,
            )

        interconnector_station.approved = False
        interconnector_station.created_by = "opennem.importer.interconnectors"

        if not interconnector_station.location:
            interconnector_station.location = Location(
                state=state_from_network_region(interconnector.regionfrom)
            )

        interconnector_station.name = interconnector.description

        # for network_region in [interconnector.regionfrom, interconnector.regionto]:
        # Fac1
        int_facility = (
            session.query(Facility)
            .filter_by(code=interconnector.interconnectorid)
            .filter_by(dispatch_type=DispatchType.GENERATOR)
            .filter_by(network_id="NEM")
            .filter_by(network_region=interconnector.regionfrom)
            .one_or_none()
        )

        if not int_facility:
            int_facility = Facility(  # type: ignore
                code=interconnector.interconnectorid,
                dispatch_type=DispatchType.GENERATOR,
                network_id="NEM",
                network_region=interconnector.regionfrom,
            )

        int_facility.status_id = "operating"
        int_facility.approved = False
        int_facility.created_by = "opennem.importer.interconnectors"
        int_facility.fueltech_id = None

        int_facility.interconnector = True
        int_facility.interconnector_region_to = interconnector.regionto

        interconnector_station.facilities.append(int_facility)

        session.add(interconnector_station)

        logger.debug("Created interconnector station: {}".format(interconnector_station.code))

    session.commit()

    return None


if __name__ == "__main__":
    import_nem_interconnects()
