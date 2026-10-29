#!/bin/bash
# HTTP DML 역할과 별도 Alembic DDL 소유자를 최초 DB 초기화 때 만든다.
set -euo pipefail
export APP_DB_PASSWORD="$(cat /run/postgresql/secrets/app-password)"
export MIGRATION_DB_PASSWORD="$(cat /run/postgresql/secrets/migration-password)"
[[ -n "$APP_DB_PASSWORD" && -n "$MIGRATION_DB_PASSWORD" ]]
# 비밀값을 명령 인자나 SQL 오류 로그에 넣지 않고 psql 표준입력으로 전달한다.
export PGPASSWORD="$POSTGRES_PASSWORD"
psql --no-psqlrc --set ON_ERROR_STOP=1 --set "POSTGRES_DB=$POSTGRES_DB" \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --quiet <<'SQL'
\getenv app_password APP_DB_PASSWORD
\getenv migration_password MIGRATION_DB_PASSWORD
CREATE ROLE dreamon_migration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'migration_password';
CREATE ROLE dreamon_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
REVOKE ALL ON DATABASE :"POSTGRES_DB" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"POSTGRES_DB" TO dreamon_app, dreamon_migration;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO dreamon_migration;
GRANT USAGE ON SCHEMA public TO dreamon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE dreamon_migration IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dreamon_app;
ALTER DEFAULT PRIVILEGES FOR ROLE dreamon_migration IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO dreamon_app;
SQL
