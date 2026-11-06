-- Run as the Shop database administrator. The new role has no login until
-- an operator assigns a password interactively after reviewing grants.
BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'healthswarm_catalog_reader') THEN
    CREATE ROLE healthswarm_catalog_reader NOLOGIN NOINHERIT;
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO healthswarm_catalog_reader', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO healthswarm_catalog_reader;
GRANT SELECT ON TABLE
  fa_shop_goods,
  fa_shop_goods_sku,
  fa_shop_category,
  fa_shop_ingredient,
  fa_shop_ingredient_alias,
  fa_shop_ingredient_sku_map,
  fa_shop_catalog_version
TO healthswarm_catalog_reader;

ALTER ROLE healthswarm_catalog_reader SET default_transaction_read_only = on;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'healthswarm_catalog_reader'
      AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit)
  ) OR EXISTS (
    SELECT 1 FROM pg_auth_members AS m
    JOIN pg_roles AS r ON r.oid = m.member
    WHERE r.rolname = 'healthswarm_catalog_reader'
  ) THEN
    RAISE EXCEPTION 'catalog reader has elevated role privileges or memberships';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
      AND CASE WHEN c.relkind IN ('r', 'p', 'v', 'm', 'f') THEN (
        ((has_table_privilege('healthswarm_catalog_reader', c.oid, 'SELECT')
           OR has_any_column_privilege('healthswarm_catalog_reader', c.oid, 'SELECT'))
         AND NOT (n.nspname = 'public' AND c.relname = ANY(ARRAY[
           'fa_shop_goods', 'fa_shop_goods_sku', 'fa_shop_category',
           'fa_shop_ingredient', 'fa_shop_ingredient_alias',
           'fa_shop_ingredient_sku_map', 'fa_shop_catalog_version'
         ])))
        OR has_table_privilege(
          'healthswarm_catalog_reader', c.oid,
          'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
        )
        OR has_any_column_privilege('healthswarm_catalog_reader', c.oid, 'INSERT,UPDATE,REFERENCES')
      ) ELSE false END
  ) OR EXISTS (
    SELECT 1 FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
      AND CASE WHEN c.relkind = 'S'
        THEN has_sequence_privilege('healthswarm_catalog_reader', c.oid, 'USAGE,SELECT,UPDATE')
        ELSE false END
  ) OR EXISTS (
    SELECT 1 FROM pg_namespace AS n
    WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
      AND has_schema_privilege('healthswarm_catalog_reader', n.oid, 'CREATE')
  ) OR EXISTS (
    SELECT 1 FROM pg_default_acl AS d
    CROSS JOIN LATERAL aclexplode(d.defaclacl) AS privilege
    WHERE privilege.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'healthswarm_catalog_reader')
  ) OR has_database_privilege('healthswarm_catalog_reader', current_database(), 'CREATE') THEN
    RAISE EXCEPTION 'catalog reader has privileges outside the seven-table SELECT allowlist';
  END IF;
END
$$;

COMMIT;
