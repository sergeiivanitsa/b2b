#!/usr/bin/env python3
"""Fail-closed PostgreSQL identity guard for the one-time fresh install.

The script is executed inside the exact Product release image.  It never
prints ``DATABASE_URL``; the raw value is represented only by its SHA-256.
``reset`` performs the guarded public-schema replacement in one transaction
and installs the approved least-privilege schema ACL.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
import re
import sys
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


EXPECTED_HEAD = "0019_company_card_v2_rollout_control"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$-]{0,62}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SERVER = re.compile(r"^[0-9A-Fa-f:.]+:[1-9][0-9]{0,4}$")


class FreshInstallDatabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpectedIdentity:
    identity_sha256: str


@dataclass(frozen=True)
class SchemaGrant:
    grantee: str
    privilege: str
    grantable: bool


@dataclass(frozen=True)
class ObservedIdentity:
    schema_version: str
    database_url_sha256: str
    database_name: str
    database_oid: int
    server_identity: str
    database_role: str
    session_role: str
    schema_owner: str
    database_owner: str
    database_acl: str | None
    server_version_num: int
    database_owner_member: bool
    schema_owner_member: bool
    schema_usage: bool
    schema_create: bool
    non_system_schemas: tuple[str, ...]
    schema_grants: tuple[SchemaGrant, ...]
    other_sessions: int


def _identifier(value: str) -> str:
    """Quote one PostgreSQL identifier without accepting qualified names."""
    if not value or "\x00" in value or len(value.encode("utf-8")) > 63:
        raise FreshInstallDatabaseError("database identifier is invalid; STOP")
    return '"' + value.replace('"', '""') + '"'


def _grant_sql(grants: Iterable[SchemaGrant]) -> tuple[str, ...]:
    statements: list[str] = ["REVOKE ALL ON SCHEMA public FROM PUBLIC"]
    for grant in sorted(grants, key=lambda item: (item.grantee, item.privilege, item.grantable)):
        if grant.privilege not in {"CREATE", "USAGE"}:
            raise FreshInstallDatabaseError("unsupported public schema privilege; STOP")
        grantee = "PUBLIC" if grant.grantee == "PUBLIC" else _identifier(grant.grantee)
        suffix = " WITH GRANT OPTION" if grant.grantable else ""
        statements.append(
            f"GRANT {grant.privilege} ON SCHEMA public TO {grantee}{suffix}"
        )
    return tuple(statements)


def _strict_grants(runtime_role: str) -> tuple[SchemaGrant, ...]:
    return (
        SchemaGrant(runtime_role, "CREATE", False),
        SchemaGrant(runtime_role, "USAGE", False),
    )


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _expected_from_environment() -> ExpectedIdentity:
    expected = ExpectedIdentity(
        identity_sha256=os.environ.get("EXPECTED_DATABASE_IDENTITY_SHA256", ""),
    )
    if _DIGEST.fullmatch(expected.identity_sha256) is None:
        raise FreshInstallDatabaseError("expected database identity digest is invalid; STOP")
    return expected


async def _observe(connection: AsyncConnection, database_url: str) -> ObservedIdentity:
    identity = (
        await connection.execute(
            text(
                """
                SELECT current_database() AS database_name,
                       d.oid::integer AS database_oid,
                       current_user AS database_role,
                       session_user AS session_role,
                       COALESCE(inet_server_addr()::text, 'local') || ':' ||
                           inet_server_port()::text AS server_identity,
                       pg_get_userbyid(d.datdba) AS database_owner,
                       d.datacl::text AS database_acl,
                       pg_get_userbyid(n.nspowner) AS schema_owner,
                       current_setting('server_version_num')::integer AS server_version_num,
                       pg_has_role(current_user, d.datdba, 'USAGE') AS database_owner_member,
                       pg_has_role(current_user, n.nspowner, 'USAGE') AS schema_owner_member,
                       has_schema_privilege(current_user, n.oid, 'USAGE') AS schema_usage,
                       has_schema_privilege(current_user, n.oid, 'CREATE') AS schema_create,
                       (SELECT count(*)::integer
                          FROM pg_stat_activity a
                         WHERE a.datname = current_database()
                           AND a.pid <> pg_backend_pid()) AS other_sessions
                  FROM pg_database d
                  JOIN pg_namespace n ON n.nspname = 'public'
                 WHERE d.datname = current_database()
                """
            )
        )
    ).mappings().one_or_none()
    if identity is None:
        raise FreshInstallDatabaseError("public schema identity is unavailable; STOP")
    grant_rows = (
        await connection.execute(
            text(
                """
                SELECT CASE WHEN acl.grantee = 0 THEN 'PUBLIC'
                            ELSE pg_get_userbyid(acl.grantee) END AS grantee,
                       acl.privilege_type AS privilege,
                       acl.is_grantable AS grantable
                  FROM pg_namespace n
                  CROSS JOIN LATERAL aclexplode(
                      COALESCE(n.nspacl, acldefault('n', n.nspowner))
                  ) AS acl
                 WHERE n.nspname = 'public'
                 ORDER BY grantee, privilege, grantable
                """
            )
        )
    ).mappings().all()
    grants = tuple(
        SchemaGrant(
            grantee=str(row["grantee"]),
            privilege=str(row["privilege"]),
            grantable=bool(row["grantable"]),
        )
        for row in grant_rows
    )
    schemas = tuple(
        str(value)
        for value in (
            await connection.execute(
                text(
                    "SELECT nspname FROM pg_namespace "
                    "WHERE nspname <> 'information_schema' "
                    "AND nspname NOT LIKE 'pg_%' ORDER BY nspname"
                )
            )
        ).scalars()
    )
    return ObservedIdentity(
        schema_version="production_fresh_install_db_identity_v1",
        database_url_sha256=sha256(database_url.encode()).hexdigest(),
        database_name=str(identity["database_name"]),
        database_oid=int(identity["database_oid"]),
        server_identity=str(identity["server_identity"]),
        database_role=str(identity["database_role"]),
        session_role=str(identity["session_role"]),
        schema_owner=str(identity["schema_owner"]),
        database_owner=str(identity["database_owner"]),
        database_acl=None if identity["database_acl"] is None else str(identity["database_acl"]),
        server_version_num=int(identity["server_version_num"]),
        database_owner_member=bool(identity["database_owner_member"]),
        schema_owner_member=bool(identity["schema_owner_member"]),
        schema_usage=bool(identity["schema_usage"]),
        schema_create=bool(identity["schema_create"]),
        non_system_schemas=schemas,
        schema_grants=grants,
        other_sessions=int(identity["other_sessions"]),
    )


def _assert_expected(observed: ObservedIdentity, expected: ExpectedIdentity) -> None:
    if _identity_digest(observed) != expected.identity_sha256:
        raise FreshInstallDatabaseError("production database identity mismatch; STOP")
    if (
        observed.database_role != observed.session_role
        or not observed.database_owner_member
        or not observed.schema_owner_member
        or not observed.schema_usage
        or not observed.schema_create
    ):
        raise FreshInstallDatabaseError("runtime role lacks exact database/schema capability; STOP")
    if observed.non_system_schemas != ("public",):
        raise FreshInstallDatabaseError("public is not the sole non-system schema; STOP")
    if not observed.schema_grants:
        raise FreshInstallDatabaseError("public schema grants are empty; STOP")


def _assert_strict_schema_contract(observed: ObservedIdentity) -> None:
    if (
        observed.schema_owner != observed.database_role
        or observed.schema_grants != _strict_grants(observed.database_role)
    ):
        raise FreshInstallDatabaseError(
            "public schema ACL is not the approved strict contract; STOP"
        )


def _identity_digest(observed: ObservedIdentity) -> str:
    identity = {
        "database_acl": observed.database_acl,
        "database_name": observed.database_name,
        "database_oid": observed.database_oid,
        "database_owner": observed.database_owner,
        "database_role": observed.database_role,
        "database_url_sha256": observed.database_url_sha256,
        "server_version_num": observed.server_version_num,
        "server_identity": observed.server_identity,
        "session_role": observed.session_role,
    }
    return sha256(_canonical(identity)).hexdigest()


def _grants_digest(grants: tuple[SchemaGrant, ...]) -> str:
    return sha256(
        _canonical({"grants": [asdict(item) for item in grants]})
    ).hexdigest()


def _schema_marker(release_sha: str, identity_sha256: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
        raise FreshInstallDatabaseError("release SHA is invalid; STOP")
    binding = sha256(f"{identity_sha256}:{release_sha}".encode()).hexdigest()
    return _canonical(
        {
            "database_identity_binding_sha256": binding,
            "release_sha": release_sha,
            "schema_version": "production_fresh_install_schema_marker_v1",
        }
    ).decode().rstrip("\n")


async def _read_schema_marker(connection: AsyncConnection) -> str | None:
    value = (
        await connection.execute(
            text(
                "SELECT obj_description(n.oid, 'pg_namespace') "
                "FROM pg_namespace n WHERE n.nspname = 'public'"
            )
        )
    ).scalar_one_or_none()
    return None if value is None else str(value)


async def _verify_fresh_head_defaults(
    connection: AsyncConnection,
    *,
    allow_superadmin: bool = False,
    allow_application_data: bool = False,
) -> None:
    publication = (
        await connection.execute(
            text(
                "SELECT id, state, policy_version "
                "FROM company_report_publication_control"
            )
        )
    ).all()
    if publication != [(1, "paused", "publication_sufficiency_v1")]:
        raise FreshInstallDatabaseError("publication control is not exact default-off; STOP")
    narrative = (
        await connection.execute(
            text(
                "SELECT singleton_id, enabled, kill_switch, daily_limit, "
                "monthly_limit, concurrency_limit, leased_count "
                "FROM company_card_narrative_runtime_control"
            )
        )
    ).all()
    if narrative != [(1, False, True, 0, 0, 0, 0)]:
        raise FreshInstallDatabaseError("narrative control is not exact default-off; STOP")
    if allow_application_data:
        return
    table_names = tuple(
        str(value)
        for value in (
            await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                )
            )
        ).scalars()
    )
    allowed_nonempty = {
        "alembic_version",
        "company_card_narrative_runtime_control",
        "company_report_publication_control",
    }
    if allow_superadmin:
        allowed_nonempty.add("users")
    for table_name in table_names:
        if table_name in allowed_nonempty:
            continue
        count = int(
            (
                await connection.execute(
                    text(f"SELECT count(*) FROM {_identifier(table_name)}")
                )
            ).scalar_one()
        )
        if count != 0:
            raise FreshInstallDatabaseError("fresh schema contains application data; STOP")


async def _schema_dependency_objects(
    connection: AsyncConnection,
) -> tuple[tuple[str, str, str, str, str], ...]:
    """Return every object PostgreSQL would reach from ``DROP SCHEMA``.

    Catalog allowlists are incomplete by construction: schema-owned objects
    also include collations, conversions, operators/opclasses/families,
    text-search objects and statistics, while policies/triggers/defaults are
    attached through dependencies.  Walking ``pg_depend`` from the namespace
    and rendering each address with ``pg_identify_object`` binds the complete
    server-owned dependency graph without relying on names or four catalogs.
    """
    rows = (
        await connection.execute(
            text(
                """
                WITH RECURSIVE object_graph(classid, objid, objsubid) AS (
                    SELECT 'pg_namespace'::regclass::oid, n.oid, 0
                      FROM pg_namespace n
                     WHERE n.nspname = 'public'
                    UNION
                    SELECT d.classid, d.objid, d.objsubid
                      FROM pg_depend d
                      JOIN object_graph parent
                        ON d.refclassid = parent.classid
                       AND d.refobjid = parent.objid
                       AND (parent.objsubid = 0 OR d.refobjsubid = parent.objsubid)
                     WHERE d.deptype <> 'p'
                )
                SELECT DISTINCT graph.classid::regclass::text AS catalog,
                       identified.type,
                       COALESCE(identified.schema, '') AS schema_name,
                       COALESCE(identified.name, '') AS object_name,
                       COALESCE(identified.identity, '') AS identity
                  FROM object_graph graph
                  CROSS JOIN LATERAL pg_identify_object(
                      graph.classid, graph.objid, graph.objsubid
                  ) AS identified
                 WHERE NOT (
                     graph.classid = 'pg_namespace'::regclass::oid
                     AND graph.objid = (
                         SELECT oid FROM pg_namespace WHERE nspname = 'public'
                     )
                     AND graph.objsubid = 0
                 )
                 ORDER BY catalog, type, schema_name, object_name, identity
                """
            )
        )
    ).all()
    return tuple(tuple(str(value) for value in row) for row in rows)


async def _schema_dependency_addresses(
    connection: AsyncConnection,
) -> frozenset[tuple[int, int, int]]:
    """Return the raw dependency closure used for fail-closed admission.

    Human-readable ``pg_identify_object`` output is suitable for receipts but
    is not a stable authorization primitive across PostgreSQL versions and
    locales.  Raw catalog addresses are compared with OIDs discovered from the
    structurally verified Alembic stub instead.
    """
    rows = (
        await connection.execute(
            text(
                """
                WITH RECURSIVE object_graph(classid, objid, objsubid) AS (
                    SELECT 'pg_namespace'::regclass::oid, n.oid, 0
                      FROM pg_namespace n
                     WHERE n.nspname = 'public'
                    UNION
                    SELECT d.classid, d.objid, d.objsubid
                      FROM pg_depend d
                      JOIN object_graph parent
                        ON d.refclassid = parent.classid
                       AND d.refobjid = parent.objid
                       AND (parent.objsubid = 0 OR d.refobjsubid = parent.objsubid)
                     WHERE d.deptype <> 'p'
                )
                SELECT DISTINCT graph.classid::bigint,
                       graph.objid::bigint,
                       graph.objsubid::integer
                  FROM object_graph graph
                 WHERE NOT (
                     graph.classid = 'pg_namespace'::regclass::oid
                     AND graph.objid = (
                         SELECT oid FROM pg_namespace WHERE nspname = 'public'
                     )
                     AND graph.objsubid = 0
                 )
                 ORDER BY 1, 2, 3
                """
            )
        )
    ).all()
    return frozenset((int(classid), int(objid), int(objsubid)) for classid, objid, objsubid in rows)


def _assert_dependency_closure(
    actual: frozenset[tuple[int, int, int]],
    allowed: frozenset[tuple[int, int, int]],
) -> None:
    if not actual.issubset(allowed):
        raise FreshInstallDatabaseError("migration source object graph is invalid; STOP")


async def _schema_state(connection: AsyncConnection) -> tuple[tuple[str, ...], str]:
    has_revision_table = bool(
        (
            await connection.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            )
        ).scalar_one()
    )
    revisions = (
        tuple(
            str(value)
            for value in (
                await connection.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                )
            ).scalars()
        )
        if has_revision_table
        else ()
    )
    rows = await _schema_dependency_objects(connection)
    inventory = {"objects": [list(row) for row in rows]}
    return revisions, sha256(_canonical(inventory)).hexdigest()


async def _verify_upgrade_source(connection: AsyncConnection) -> None:
    revisions, _ = await _schema_state(connection)
    if revisions:
        raise FreshInstallDatabaseError("migration source already has a revision; STOP")
    objects = await _schema_dependency_objects(connection)
    addresses = await _schema_dependency_addresses(connection)
    if not objects and not addresses:
        return
    if not objects or not addresses:
        raise FreshInstallDatabaseError("migration source object graph is invalid; STOP")

    columns = (
        await connection.execute(
            text(
                "SELECT column_name, data_type, is_nullable, "
                "character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'alembic_version' "
                "ORDER BY ordinal_position"
            )
        )
    ).all()
    if columns != [("version_num", "character varying", "NO", 64)]:
        raise FreshInstallDatabaseError("Alembic bootstrap table is invalid; STOP")
    count = int(
        (await connection.execute(text("SELECT count(*) FROM alembic_version"))).scalar_one()
    )
    if count != 0:
        raise FreshInstallDatabaseError("Alembic bootstrap table is not empty; STOP")

    # Discover the sanctioned catalog OIDs from the exact stub structure.  Do
    # not authorize by rendered object names: pg_identify_object output is
    # deliberately receipt-only and can vary with server version/locale.
    shape = (
        await connection.execute(
            text(
                """
                SELECT 'pg_class'::regclass::oid::bigint AS pg_class_catalog,
                       'pg_type'::regclass::oid::bigint AS pg_type_catalog,
                       'pg_constraint'::regclass::oid::bigint AS pg_constraint_catalog,
                       table_class.oid::bigint AS table_oid,
                       table_class.reltype::bigint AS row_type_oid,
                       row_type.typarray::bigint AS array_type_oid,
                       attribute.attnum::integer AS column_number,
                       index_class.oid::bigint AS index_oid,
                       constraint_row.oid::bigint AS constraint_oid,
                       table_class.relkind::text,
                       table_class.relpersistence::text,
                       table_class.relispartition,
                       table_class.relhasrules,
                       table_class.relhastriggers,
                       table_class.relrowsecurity,
                       table_class.relforcerowsecurity,
                       pg_get_userbyid(table_class.relowner) = current_user AS owned_by_runtime,
                       attribute.attnotnull,
                       attribute.attisdropped,
                       attribute.atttypid = 'character varying'::regtype AS varchar_column,
                       attribute.atttypmod::integer,
                       constraint_row.conname,
                       constraint_row.contype::text,
                       constraint_row.conkey::text,
                       constraint_row.convalidated,
                       constraint_row.condeferrable,
                       constraint_row.condeferred,
                       constraint_row.conparentid::bigint,
                       index_row.indisprimary,
                       index_row.indisunique,
                       index_row.indisvalid,
                       index_row.indisready,
                       index_row.indislive,
                       index_row.indisexclusion,
                       index_row.indnatts::integer,
                       index_row.indnkeyatts::integer,
                       index_row.indkey::text,
                       index_row.indexprs IS NULL,
                       index_row.indpred IS NULL,
                       index_class.relkind::text,
                       index_class.relpersistence::text,
                       index_class.relispartition
                  FROM pg_class table_class
                  JOIN pg_namespace namespace
                    ON namespace.oid = table_class.relnamespace
                  JOIN pg_type row_type ON row_type.oid = table_class.reltype
                  JOIN pg_attribute attribute
                    ON attribute.attrelid = table_class.oid
                   AND attribute.attname = 'version_num'
                   AND attribute.attnum > 0
                  JOIN pg_constraint constraint_row
                    ON constraint_row.conrelid = table_class.oid
                  JOIN pg_index index_row
                    ON index_row.indrelid = table_class.oid
                   AND index_row.indexrelid = constraint_row.conindid
                  JOIN pg_class index_class ON index_class.oid = index_row.indexrelid
                 WHERE namespace.nspname = 'public'
                   AND table_class.relname = 'alembic_version'
                """
            )
        )
    ).all()
    if len(shape) != 1:
        raise FreshInstallDatabaseError("Alembic bootstrap structure is invalid; STOP")
    row = shape[0]
    (
        pg_class_catalog,
        pg_type_catalog,
        pg_constraint_catalog,
        table_oid,
        row_type_oid,
        array_type_oid,
        column_number,
        index_oid,
        constraint_oid,
        table_relkind,
        table_persistence,
        table_partition,
        table_rules,
        table_triggers,
        row_security,
        forced_row_security,
        owned_by_runtime,
        column_not_null,
        column_dropped,
        varchar_column,
        column_typmod,
        constraint_name,
        constraint_type,
        constraint_keys,
        constraint_validated,
        constraint_deferrable,
        constraint_deferred,
        constraint_parent,
        index_primary,
        index_unique,
        index_valid,
        index_ready,
        index_live,
        index_exclusion,
        index_attributes,
        index_key_attributes,
        index_keys,
        index_expression_absent,
        index_predicate_absent,
        index_relkind,
        index_persistence,
        index_partition,
    ) = row
    exact_shape = (
        str(table_relkind) == "r"
        and str(table_persistence) == "p"
        and not bool(table_partition)
        and not bool(table_rules)
        and not bool(table_triggers)
        and not bool(row_security)
        and not bool(forced_row_security)
        and bool(owned_by_runtime)
        and int(column_number) == 1
        and bool(column_not_null)
        and not bool(column_dropped)
        and bool(varchar_column)
        and int(column_typmod) == 68
        and str(constraint_name) == "alembic_version_pkc"
        and str(constraint_type) == "p"
        and str(constraint_keys) == "{1}"
        and bool(constraint_validated)
        and not bool(constraint_deferrable)
        and not bool(constraint_deferred)
        and int(constraint_parent) == 0
        and bool(index_primary)
        and bool(index_unique)
        and bool(index_valid)
        and bool(index_ready)
        and bool(index_live)
        and not bool(index_exclusion)
        and int(index_attributes) == 1
        and int(index_key_attributes) == 1
        and str(index_keys).strip() == "1"
        and bool(index_expression_absent)
        and bool(index_predicate_absent)
        and str(index_relkind) == "i"
        and str(index_persistence) == "p"
        and not bool(index_partition)
    )
    if not exact_shape:
        raise FreshInstallDatabaseError("Alembic bootstrap structure is invalid; STOP")

    attached_counts = (
        await connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM pg_trigger
                      WHERE tgrelid = :table_oid AND NOT tgisinternal),
                    (SELECT count(*) FROM pg_policy
                      WHERE polrelid = :table_oid),
                    (SELECT count(*) FROM pg_collation collation
                      JOIN pg_namespace namespace
                        ON namespace.oid = collation.collnamespace
                      WHERE namespace.nspname = 'public'),
                    (SELECT count(*) FROM pg_rewrite
                      WHERE ev_class = :table_oid),
                    (SELECT count(*) FROM pg_attrdef
                      WHERE adrelid = :table_oid),
                    (SELECT count(*) FROM pg_statistic_ext
                      WHERE stxrelid = :table_oid),
                    (SELECT count(*) FROM pg_inherits
                      WHERE inhrelid = :table_oid OR inhparent = :table_oid),
                    (SELECT count(*) FROM pg_publication_rel
                      WHERE prrelid = :table_oid)
                """
            ),
            {"table_oid": int(table_oid)},
        )
    ).one()
    if any(int(value) != 0 for value in attached_counts):
        raise FreshInstallDatabaseError("Alembic bootstrap has attached objects; STOP")

    allowed = frozenset(
        {
            (int(pg_class_catalog), int(table_oid), 0),
            (int(pg_class_catalog), int(table_oid), int(column_number)),
            (int(pg_class_catalog), int(index_oid), 0),
            (int(pg_class_catalog), int(index_oid), 1),
            (int(pg_type_catalog), int(row_type_oid), 0),
            (int(pg_type_catalog), int(array_type_oid), 0),
            (int(pg_constraint_catalog), int(constraint_oid), 0),
        }
    )
    _assert_dependency_closure(addresses, allowed)


def _receipt(
    observed: ObservedIdentity,
    *,
    phase: str,
    release_sha: str,
    revisions: tuple[str, ...],
    inventory_sha256: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise FreshInstallDatabaseError("release SHA is invalid; STOP")
    return {
        "alembic_revisions": list(revisions),
        "other_sessions": observed.other_sessions,
        "phase": phase,
        "release_sha": release_sha,
        "schema_grants_sha256": _grants_digest(observed.schema_grants),
        "schema_inventory_sha256": inventory_sha256,
        "schema_version": "production_fresh_install_db_receipt_v1",
    }


async def _run(command: str, release_sha: str) -> dict[str, Any]:
    from product_api.settings import get_settings

    if re.fullmatch(r"[0-9a-f]{40}", release_sha) is None:
        raise FreshInstallDatabaseError("release SHA is invalid; STOP")
    database_url = get_settings().database_url
    expected = None if command == "fingerprint" else _expected_from_environment()
    engine = create_async_engine(database_url, pool_pre_ping=False)
    try:
        if command in {"fingerprint", "inspect"}:
            async with engine.connect() as connection:
                observed = await _observe(connection, database_url)
                revisions, inventory = await _schema_state(connection)
                if command == "inspect":
                    assert expected is not None
                    _assert_expected(observed, expected)
                    if revisions != ("0015_claims_company_report_handoff",):
                        raise FreshInstallDatabaseError(
                            "database is not exact sole legacy revision 0015; STOP"
                        )
            payload = _receipt(
                observed,
                phase="fingerprint" if command == "fingerprint" else "preflight",
                release_sha=release_sha,
                revisions=revisions,
                inventory_sha256=inventory,
            )
            # Fingerprinting is an explicit operator-only discovery command.
            # The protected digest is deliberately omitted from every staged
            # preflight/reset/migration receipt so it cannot become a reusable
            # credential through an artifact or deploy directory.
            if command == "fingerprint":
                payload["database_identity_sha256"] = _identity_digest(observed)
            return payload

        if command == "reset":
            assert expected is not None
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL lock_timeout = '10s'"))
                await connection.execute(text("SET LOCAL statement_timeout = '120s'"))
                observed = await _observe(connection, database_url)
                _assert_expected(observed, expected)
                revisions, inventory = await _schema_state(connection)
                expected_inventory = os.environ.get(
                    "EXPECTED_SCHEMA_INVENTORY_SHA256", ""
                )
                if _DIGEST.fullmatch(expected_inventory) is None:
                    raise FreshInstallDatabaseError("preflight schema digest invalid; STOP")
                if observed.other_sessions != 0:
                    raise FreshInstallDatabaseError(
                        "database still has other sessions after writer shutdown; STOP"
                    )
                empty_inventory = sha256(_canonical({"objects": []})).hexdigest()
                marker = _schema_marker(release_sha, expected.identity_sha256)
                strict_grants = _strict_grants(observed.database_role)
                if revisions == ("0015_claims_company_report_handoff",) and inventory == expected_inventory:
                    await connection.execute(text("DROP SCHEMA public CASCADE"))
                    await connection.execute(text("CREATE SCHEMA public AUTHORIZATION CURRENT_USER"))
                    for statement in _grant_sql(strict_grants):
                        await connection.execute(text(statement))
                    quoted_marker = marker.replace("'", "''")
                    await connection.execute(
                        text(f"COMMENT ON SCHEMA public IS '{quoted_marker}'")
                    )
                elif not revisions and inventory == empty_inventory:
                    if observed.schema_owner != observed.database_role or observed.schema_grants != strict_grants:
                        raise FreshInstallDatabaseError("reconciled public schema grants mismatch; STOP")
                    if await _read_schema_marker(connection) != marker:
                        raise FreshInstallDatabaseError("reconciled schema marker mismatch; STOP")
                else:
                    raise FreshInstallDatabaseError(
                        "database changed outside the exact reset reconciliation states; STOP"
                    )
            async with engine.connect() as connection:
                reset_observed = await _observe(connection, database_url)
                _assert_expected(reset_observed, expected)
                _assert_strict_schema_contract(reset_observed)
                if await _read_schema_marker(connection) != _schema_marker(
                    release_sha, expected.identity_sha256
                ):
                    raise FreshInstallDatabaseError("database schema reset marker missing; STOP")
                reset_revisions, reset_inventory = await _schema_state(connection)
                empty_inventory = sha256(_canonical({"objects": []})).hexdigest()
                if reset_revisions or reset_inventory != empty_inventory:
                    raise FreshInstallDatabaseError("fresh public schema is not empty; STOP")
            return _receipt(
                reset_observed,
                phase="schema-reset",
                release_sha=release_sha,
                revisions=(),
                inventory_sha256=reset_inventory,
            )

        if command == "verify-reset":
            assert expected is not None
            async with engine.connect() as connection:
                observed = await _observe(connection, database_url)
                _assert_expected(observed, expected)
                _assert_strict_schema_contract(observed)
                revisions, inventory = await _schema_state(connection)
                empty_inventory = sha256(_canonical({"objects": []})).hexdigest()
                if revisions or inventory != empty_inventory:
                    raise FreshInstallDatabaseError("database is not exact reset schema; STOP")
                if observed.other_sessions != 0:
                    raise FreshInstallDatabaseError("reset database has unexpected sessions; STOP")
                if await _read_schema_marker(connection) != _schema_marker(release_sha, expected.identity_sha256):
                    raise FreshInstallDatabaseError("reset database marker identity mismatch; STOP")
            return _receipt(
                observed,
                phase="schema-reset-verified",
                release_sha=release_sha,
                revisions=revisions,
                inventory_sha256=inventory,
            )

        if command == "prepare-upgrade":
            assert expected is not None
            async with engine.connect() as connection:
                observed = await _observe(connection, database_url)
                _assert_expected(observed, expected)
                _assert_strict_schema_contract(observed)
                if observed.other_sessions != 0:
                    raise FreshInstallDatabaseError(
                        "migration source has unexpected sessions; STOP"
                    )
                if await _read_schema_marker(connection) != _schema_marker(
                    release_sha, expected.identity_sha256
                ):
                    raise FreshInstallDatabaseError(
                        "migration source marker identity mismatch; STOP"
                    )
                await _verify_upgrade_source(connection)
                revisions, inventory = await _schema_state(connection)
            return _receipt(
                observed,
                phase="migration-source-verified",
                release_sha=release_sha,
                revisions=revisions,
                inventory_sha256=inventory,
            )

        if command in {"verify-head", "verify-runtime", "verify-live-runtime"}:
            assert expected is not None
            async with engine.connect() as connection:
                observed = await _observe(connection, database_url)
                _assert_expected(observed, expected)
                _assert_strict_schema_contract(observed)
                revisions, inventory = await _schema_state(connection)
                if revisions != (EXPECTED_HEAD,):
                    raise FreshInstallDatabaseError("database is not at exact sole head 0019; STOP")
                if await _read_schema_marker(connection) != _schema_marker(
                    release_sha, expected.identity_sha256
                ):
                    raise FreshInstallDatabaseError("database schema marker identity mismatch; STOP")
                await _verify_fresh_head_defaults(
                    connection,
                    allow_superadmin=command == "verify-runtime",
                    allow_application_data=command == "verify-live-runtime",
                )
                if command in {"verify-runtime", "verify-live-runtime"}:
                    settings = get_settings()
                    expected_email = settings.superadmin_email or ""
                    if (
                        not expected_email
                        or expected_email != expected_email.strip()
                        or len(expected_email) > 320
                    ):
                        raise FreshInstallDatabaseError(
                            "SUPERADMIN_EMAIL is absent after Product startup; STOP"
                        )
                    if command == "verify-runtime":
                        users = (
                            await connection.execute(
                                text(
                                    "SELECT email, is_superadmin, role, is_active, "
                                    "company_id, first_name, last_name, joined_company_at "
                                    "FROM users ORDER BY id"
                                )
                            )
                        ).all()
                        if users != [
                            (expected_email, True, None, True, None, None, None, None)
                        ]:
                            raise FreshInstallDatabaseError(
                                "initial superadmin bootstrap is not exact; STOP"
                            )
                    else:
                        superadmins = (
                            await connection.execute(
                                text(
                                    "SELECT email, is_active FROM users "
                                    "WHERE is_superadmin ORDER BY id"
                                )
                            )
                        ).all()
                        if superadmins != [(expected_email, True)]:
                            raise FreshInstallDatabaseError(
                                "live runtime superadmin identity is not exact; STOP"
                            )
            return _receipt(
                observed,
                phase=(
                    "runtime-verified"
                    if command == "verify-runtime"
                    else (
                        "live-runtime-verified"
                        if command == "verify-live-runtime"
                        else "migration-complete"
                    )
                ),
                release_sha=release_sha,
                revisions=revisions,
                inventory_sha256=inventory,
            )
        raise FreshInstallDatabaseError("unknown database guard command; STOP")
    finally:
        await engine.dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "fingerprint",
            "inspect",
            "reset",
            "verify-reset",
            "prepare-upgrade",
            "verify-head",
            "verify-runtime",
            "verify-live-runtime",
        ),
    )
    parser.add_argument("--release-sha", required=True)
    args = parser.parse_args(argv[1:])
    try:
        payload = asyncio.run(_run(args.command, args.release_sha))
        encoded = _canonical(payload)
        sys.stdout.buffer.write(encoded)
    except FreshInstallDatabaseError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError:
        print("database operation failed without a verified receipt; STOP", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("database operation failed without a verified receipt; STOP", file=sys.stderr)
        return 2
    except Exception:
        print("database verification failed without details; STOP", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
