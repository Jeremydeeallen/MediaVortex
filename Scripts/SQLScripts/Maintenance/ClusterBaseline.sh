#!/usr/bin/env bash
# directive: db-maintenance-no-partition
# One-time PostgreSQL cluster bringup for the standard maintenance stack.
# Run AS ROOT on the database host (CT 203 for the MediaVortex cluster).
# Idempotent: re-running on an already-configured cluster makes no changes.
# Requires: WebService + WorkerService stopped (cluster restart ~30s).

set -euo pipefail

PG_VERSION="${PG_VERSION:-16}"
PG_CLUSTER="${PG_CLUSTER:-main}"
PG_DBNAME="${PG_DBNAME:-mediavortex}"
PG_CONF="/etc/postgresql/${PG_VERSION}/${PG_CLUSTER}/postgresql.conf"
TS="$(date +%Y%m%d_%H%M%S)"

echo "==> Cluster baseline: PG${PG_VERSION}/${PG_CLUSTER} db=${PG_DBNAME}"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: must run as root (apt + systemctl + postgresql.conf edit)" >&2
  exit 1
fi

if [[ ! -f "${PG_CONF}" ]]; then
  echo "ERROR: postgresql.conf not found at ${PG_CONF}" >&2
  exit 1
fi

echo "==> [1/5] apt install extension packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  "postgresql-${PG_VERSION}-cron" \
  "postgresql-${PG_VERSION}-repack"

echo "==> [2/5] postgresql.conf edit (idempotent)"
if grep -qE "^shared_preload_libraries\s*=\s*'.*pg_cron.*'" "${PG_CONF}"; then
  echo "    shared_preload_libraries already contains pg_cron -- skipping"
else
  cp -a "${PG_CONF}" "${PG_CONF}.bak.${TS}"
  echo "    backup: ${PG_CONF}.bak.${TS}"
  # Strip any existing shared_preload_libraries line (commented or not), then append ours.
  sed -i -E "/^[#[:space:]]*shared_preload_libraries\s*=/d" "${PG_CONF}"
  {
    echo ""
    echo "# directive: db-maintenance-no-partition (${TS})"
    echo "shared_preload_libraries = 'pg_cron'"
    echo "cron.database_name = '${PG_DBNAME}'"
    echo "cron.timezone = 'UTC'"
  } >> "${PG_CONF}"
  echo "    appended pg_cron preload + cron.database_name + cron.timezone"
fi

echo "==> [3/5] postgresql.conf syntax check"
# Use pg_ctlcluster to test config syntax without restarting.
sudo -u postgres /usr/lib/postgresql/${PG_VERSION}/bin/postgres \
  --config-file="${PG_CONF}" -C shared_preload_libraries >/dev/null 2>&1 || {
  echo "ERROR: postgresql.conf failed syntax check; rolling back" >&2
  if [[ -f "${PG_CONF}.bak.${TS}" ]]; then
    cp -a "${PG_CONF}.bak.${TS}" "${PG_CONF}"
    echo "    restored from ${PG_CONF}.bak.${TS}" >&2
  fi
  exit 1
}

echo "==> [4/5] restart cluster"
systemctl restart "postgresql@${PG_VERSION}-${PG_CLUSTER}"
# Wait briefly for the cluster to accept connections.
for i in 1 2 3 4 5 6 7 8 9 10; do
  if sudo -u postgres psql -d "${PG_DBNAME}" -tAc "SELECT 1" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> [5/5] CREATE EXTENSION (idempotent)"
sudo -u postgres psql -d "${PG_DBNAME}" -v ON_ERROR_STOP=1 <<-SQL
  CREATE EXTENSION IF NOT EXISTS pg_cron;
  CREATE EXTENSION IF NOT EXISTS pgstattuple;
SQL

# pg_repack is a client-side tool plus a schema-installed extension; install
# the schema half here, the CLI binary came with the apt package above.
sudo -u postgres psql -d "${PG_DBNAME}" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS pg_repack;"

echo "==> Audit"
sudo -u postgres psql -d "${PG_DBNAME}" -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('pg_cron','pg_repack','pgstattuple') ORDER BY extname;"
sudo -u postgres psql -d "${PG_DBNAME}" -c "SHOW shared_preload_libraries;"
sudo -u postgres psql -d "${PG_DBNAME}" -c "SHOW cron.database_name;"
sudo -u postgres psql -d "${PG_DBNAME}" -c "SHOW cron.timezone;"

echo "==> DONE. Next: psql -d ${PG_DBNAME} -f AutovacuumTuning.sql && psql -d ${PG_DBNAME} -f MaintenancePolicies.sql"
