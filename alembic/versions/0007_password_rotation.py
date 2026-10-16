"""Require password changes every 30 days."""
from alembic import op
import sqlalchemy as sa


revision = "0007_password_rotation"
down_revision = "0006_legacy_source_phone"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "password_changed_at" not in columns:
        op.add_column(
            "users",
            sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "password_changed_at" in columns:
        op.drop_column("users", "password_changed_at")
