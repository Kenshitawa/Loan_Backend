"""Preserve the original portfolio contact value on legacy snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0006_legacy_source_phone"
down_revision = "0005_legacy_portfolio_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("legacy_portfolio_loans")}
    if "source_phone" not in columns:
        op.add_column(
            "legacy_portfolio_loans",
            sa.Column("source_phone", sa.String(length=80), nullable=False, server_default=""),
        )


def downgrade():
    # Keep imported contact data even if the application code is rolled back.
    pass
