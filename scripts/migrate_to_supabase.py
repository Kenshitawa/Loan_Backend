"""Copy the existing Render PostgreSQL data into an empty Supabase database.

This runs only when MIGRATE_TO_SUPABASE=1 is explicitly set on the Render
service. It requires the target schema to have already been created by Alembic.
The copy is one transaction and aborts if the target contains application rows.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import MetaData, create_engine, func, make_url, select, text

from app.main import Base


def normalize_url(raw: str) -> str | URL:
    url = make_url(raw)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("Both migration databases must be PostgreSQL")
    return url


def dependency_order(tables):
    names = set(tables)
    dependencies = {name: set() for name in names}
    for name, table in tables.items():
        for fk in table.foreign_keys:
            parent = fk.column.table.name
            if parent in names and parent != name:
                dependencies[name].add(parent)
    order = []
    while dependencies:
        ready = sorted(name for name, deps in dependencies.items() if not deps)
        if not ready:
            raise RuntimeError("Foreign key cycle found; refusing an unsafe copy")
        order.extend(ready)
        for name in ready:
            dependencies.pop(name)
        for deps in dependencies.values():
            deps.difference_update(ready)
    return order


def main() -> None:
    source_raw = os.environ.get("MIGRATION_SOURCE_DATABASE_URL")
    target_raw = os.environ.get("SUPABASE_DATABASE_URL")
    if not source_raw or not target_raw:
        raise RuntimeError("Set the source and Supabase database URLs in Render")

    source_engine = create_engine(normalize_url(source_raw), pool_pre_ping=True)
    target_engine = create_engine(normalize_url(target_raw), pool_pre_ping=True)
    try:
        application_tables = sorted(Base.metadata.tables)
        source_meta = MetaData()
        target_meta = MetaData()
        source_meta.reflect(bind=source_engine, schema="public", only=application_tables)
        target_meta.reflect(bind=target_engine, schema="public", only=application_tables)
        source_tables = {
            table.name: table
            for table in source_meta.tables.values()
            if table.schema == "public"
        }
        target_tables = {
            table.name: table
            for table in target_meta.tables.values()
            if table.schema == "public"
        }
        if not source_tables:
            raise RuntimeError("Source database has no application tables")
        missing = sorted(set(source_tables) - set(target_tables))
        if missing:
            raise RuntimeError(f"Target schema is missing tables: {', '.join(missing)}")

        with source_engine.connect().execution_options(isolation_level="REPEATABLE READ") as source, target_engine.begin() as target:
            for name in source_tables:
                existing = target.execute(
                    select(func.count()).select_from(target_tables[name])
                ).scalar_one()
                if existing:
                    raise RuntimeError(f"Target table {name} is not empty; no data was copied")

            counts: dict[str, int] = {}
            for name in dependency_order(source_tables):
                src_table = source_tables[name]
                dst_table = target_tables[name]
                source_columns = {column.name for column in src_table.columns}
                target_columns = {column.name for column in dst_table.columns}
                if source_columns != target_columns:
                    raise RuntimeError(f"Column mismatch in table {name}; refusing a partial copy")
                count = 0
                result = source.execution_options(stream_results=True).execute(select(src_table))
                while rows := result.fetchmany(250):
                    target.execute(dst_table.insert(), [dict(row._mapping) for row in rows])
                    count += len(rows)
                counts[name] = count

            for name, table in target_tables.items():
                primary_keys = list(table.primary_key.columns)
                if len(primary_keys) != 1:
                    continue
                column = primary_keys[0]
                seq = target.execute(
                    text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
                    {"table_name": f'public."{name}"', "column_name": column.name},
                ).scalar_one_or_none()
                if seq:
                    max_value = target.execute(select(column).order_by(column.desc()).limit(1)).scalar_one_or_none()
                    target.execute(
                        text("SELECT setval(CAST(:sequence AS regclass), :value, :called)"),
                        {"sequence": seq, "value": max_value or 1, "called": max_value is not None},
                    )

            for name, count in counts.items():
                copied = target.execute(
                    select(func.count()).select_from(target_tables[name])
                ).scalar_one()
                if copied != count:
                    raise RuntimeError(f"Verification failed for {name}: source={count}, target={copied}")
        print("Supabase data copy completed. Row counts:")
        for name, count in sorted(counts.items()):
            print(f"  {name}: {count}")
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Error messages must never include database URLs or row contents.
        print(f"Supabase data migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
