"""Add forced password changes and customer profile records."""
from alembic import op
import sqlalchemy as sa

revision="0003_customer_profiles_and_forced_password"
down_revision="0002_collection_assignment"
branch_labels=None
depends_on=None

def upgrade():
    inspector=sa.inspect(op.get_bind())
    if "must_change_password" not in {c["name"] for c in inspector.get_columns("users")}:
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("must_change_password",sa.Boolean(),nullable=False,server_default=sa.false()))
    if "document_type" not in {c["name"] for c in inspector.get_columns("customer_documents")}:
        with op.batch_alter_table("customer_documents") as batch:
            batch.add_column(sa.Column("document_type",sa.String(length=40),nullable=False,server_default="other"))
    if not inspector.has_table("customer_interactions"):
        op.create_table("customer_interactions",
        sa.Column("customer_id",sa.Integer(),nullable=False),
        sa.Column("user_id",sa.Integer(),nullable=False),
        sa.Column("interaction_type",sa.String(length=30),nullable=False),
        sa.Column("summary",sa.Text(),nullable=False),
        sa.Column("direction",sa.String(length=20),nullable=False,server_default="outbound"),
        sa.Column("follow_up",sa.Date(),nullable=True),
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("organization_id",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("branch_id",sa.Integer(),nullable=False,server_default="1"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["customer_id"],["customers.id"]),
        sa.ForeignKeyConstraint(["user_id"],["users.id"]),
        )
    inspector=sa.inspect(op.get_bind())
    existing={i["name"] for i in inspector.get_indexes("customer_interactions")}
    if "ix_customer_interactions_customer_id" not in existing: op.create_index("ix_customer_interactions_customer_id","customer_interactions",["customer_id"])
    if "ix_customer_interactions_user_id" not in existing: op.create_index("ix_customer_interactions_user_id","customer_interactions",["user_id"])
    if "ix_customer_interactions_follow_up" not in existing: op.create_index("ix_customer_interactions_follow_up","customer_interactions",["follow_up"])

def downgrade():
    op.drop_index("ix_customer_interactions_follow_up",table_name="customer_interactions")
    op.drop_index("ix_customer_interactions_user_id",table_name="customer_interactions")
    op.drop_index("ix_customer_interactions_customer_id",table_name="customer_interactions")
    op.drop_table("customer_interactions")
    with op.batch_alter_table("customer_documents") as batch:
        batch.drop_column("document_type")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("must_change_password")
