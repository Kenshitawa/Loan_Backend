"""Allow incomplete imported customer KYC and store legacy snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0005_legacy_portfolio_snapshots"
down_revision = "0004_manager_and_payment_review"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    customer_columns = {column["name"]: column for column in inspector.get_columns("customers")}
    if not customer_columns["national_id"]["nullable"] or not customer_columns["phone"]["nullable"]:
        with op.batch_alter_table("customers") as batch:
            batch.alter_column("national_id", existing_type=sa.String(length=40), nullable=True)
            batch.alter_column("phone", existing_type=sa.String(length=30), nullable=True)
    # The baseline migration uses current model metadata, so a fresh install
    # may already have this table. Existing installations at revision 0004 do not.
    if "legacy_portfolio_loans" not in inspector.get_table_names():
        op.create_table(
        "legacy_portfolio_loans",
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("source_sheet", sa.String(length=80), nullable=False, server_default="Entire"),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_date", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("principal_cents", sa.Integer(), nullable=True),
        sa.Column("total_due_cents", sa.Integer(), nullable=True),
        sa.Column("balance_cents", sa.Integer(), nullable=True),
        sa.Column("balance_formula", sa.Text(), nullable=False, server_default=""),
        sa.Column("balance_is_formula", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_payment", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("guarantor", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("guarantor_phone", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("branch_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.UniqueConstraint("organization_id", "source_key", name="uq_legacy_portfolio_loans_organization_id"),
        )
        op.create_index("ix_legacy_portfolio_loans_customer_id", "legacy_portfolio_loans", ["customer_id"])
        op.create_index("ix_legacy_portfolio_loans_organization_id", "legacy_portfolio_loans", ["organization_id"])
        op.create_index("ix_legacy_portfolio_loans_branch_id", "legacy_portfolio_loans", ["branch_id"])


def downgrade():
    op.drop_index("ix_legacy_portfolio_loans_branch_id", table_name="legacy_portfolio_loans")
    op.drop_index("ix_legacy_portfolio_loans_organization_id", table_name="legacy_portfolio_loans")
    op.drop_index("ix_legacy_portfolio_loans_customer_id", table_name="legacy_portfolio_loans")
    op.drop_table("legacy_portfolio_loans")
    with op.batch_alter_table("customers") as batch:
        batch.alter_column("national_id", existing_type=sa.String(length=40), nullable=False)
        batch.alter_column("phone", existing_type=sa.String(length=30), nullable=False)
