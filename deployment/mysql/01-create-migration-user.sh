#!/usr/bin/env bash
# Runs only while the official MySQL image initializes a new data volume.
set -Eeuo pipefail

: "${MYSQL_DATABASE:?MYSQL_DATABASE is required}"
: "${SKYBEAT_MYSQL_MIGRATION_USER:?SKYBEAT_MYSQL_MIGRATION_USER is required}"
: "${SKYBEAT_MYSQL_MIGRATION_PASSWORD:?SKYBEAT_MYSQL_MIGRATION_PASSWORD is required}"

if [[ ! "${MYSQL_DATABASE}" =~ ^[A-Za-z0-9_]+$ ]] || [[ ! "${SKYBEAT_MYSQL_MIGRATION_USER}" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "MySQL database and migration user must contain only letters, numbers, and underscores." >&2
    exit 1
fi

escape_sql_literal() {
    sed "s/'/''/g" <<<"$1"
}

migration_password="$(escape_sql_literal "${SKYBEAT_MYSQL_MIGRATION_PASSWORD}")"

mysql --protocol=socket -uroot <<SQL
CREATE USER IF NOT EXISTS '${SKYBEAT_MYSQL_MIGRATION_USER}'@'%' IDENTIFIED BY '${migration_password}';
GRANT ALTER, CREATE, CREATE VIEW, DELETE, DROP, INDEX, INSERT, REFERENCES, SELECT, SHOW VIEW, TRIGGER, UPDATE ON \`${MYSQL_DATABASE}\`.* TO '${SKYBEAT_MYSQL_MIGRATION_USER}'@'%';
SQL
