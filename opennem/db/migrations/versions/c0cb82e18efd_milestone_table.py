# pylint: disable=no-member
"""
milestone table

Revision ID: c0cb82e18efd
Revises: 4e4fb94633e6
Create Date: 2023-11-28 09:07:31.837781

"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c0cb82e18efd"
down_revision = "4e4fb94633e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "milestones",
        sa.Column(
            "instance_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dtime", sa.DateTime(), nullable=False),
        sa.Column(
            "record_type",
            sa.Enum("low", "average", "high", name="milestonetype"),
            nullable=False,
        ),
        sa.Column("significance", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=True),
        sa.Column("network_id", sa.Integer(), nullable=True),
        sa.Column("fueltech_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facility.id"],
        ),
        sa.ForeignKeyConstraint(
            ["fueltech_id"],
            ["fueltech.code"],
        ),
        sa.ForeignKeyConstraint(
            ["network_id"],
            ["network.code"],
        ),
        sa.PrimaryKeyConstraint("instance_id", "record_id"),
    )
    op.drop_constraint("fk_facility_station_code", "facility", type_="foreignkey")
    op.create_foreign_key(
        "fk_facility_station_code",
        "facility",
        "station",
        ["station_id"],
        ["id"],
    )
    op.create_index(
        "idx_location_boundary",
        "location",
        ["boundary"],
        unique=False,
        postgresql_using="gist",
    )
    op.drop_index("ix_station_code", table_name="station")
    op.create_index(op.f("ix_station_code"), "station", ["code"], unique=True)
    op.drop_index("ix_stats_country_type", table_name="stats")
    op.drop_index("ix_stats_date", table_name="stats")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index("ix_stats_date", "stats", [sa.text("stat_date DESC")], unique=False)
    op.create_index(
        "ix_stats_country_type",
        "stats",
        ["stat_type", "country"],
        unique=False,
    )
    op.drop_index(op.f("ix_station_code"), table_name="station")
    op.create_index("ix_station_code", "station", ["code"], unique=False)
    op.drop_index("idx_location_boundary", table_name="location", postgresql_using="gist")
    op.drop_constraint("fk_facility_station_code", "facility", type_="foreignkey")
    op.create_foreign_key(
        "fk_facility_station_code",
        "facility",
        "station",
        ["station_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_table("milestones")
    # ### end Alembic commands ###