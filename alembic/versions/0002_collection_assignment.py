"""Add loan collection officer assignment."""
from alembic import op
import sqlalchemy as sa

revision="0002_collection_assignment"
down_revision="0001_initial"
branch_labels=None
depends_on=None

def upgrade():
    inspector=sa.inspect(op.get_bind())
    columns={c["name"] for c in inspector.get_columns("loans")}
    indexes={i["name"] for i in inspector.get_indexes("loans")}
    if "assigned_collector_id" not in columns:
        with op.batch_alter_table("loans") as batch:
            batch.add_column(sa.Column("assigned_collector_id",sa.Integer(),nullable=True))
            batch.create_foreign_key("fk_loans_assigned_collector_id_users","users",["assigned_collector_id"],["id"])
    if "ix_loans_assigned_collector_id" not in indexes:
        op.create_index("ix_loans_assigned_collector_id","loans",["assigned_collector_id"])

def downgrade():
    with op.batch_alter_table("loans") as batch:
        batch.drop_index("ix_loans_assigned_collector_id")
        batch.drop_constraint("fk_loans_assigned_collector_id_users",type_="foreignkey")
        batch.drop_column("assigned_collector_id")
