# PostgreSQL connector compatibility

`Pgsql.php` retains the upstream Apache-2.0 header and replaces the obsolete
`table_msg()` metadata query with PostgreSQL catalog queries. It recognizes
identity columns, schema-qualified names, primary keys and savepoints.

The expected unpatched file is from fastadminnet/framework commit
`e95df87aa1a37e83d7c5fb29722cc70967feb54b`, pinned by composer.lock.
Composer post-install/update runs scripts/apply-runtime-patches.php. That script
accepts only the recorded upstream SHA256 or the already-patched file; a framework
upgrade must explicitly review and refresh the patch and its fixture.
