# Compose deployment

## S11 production launch contract

The base Compose file is for local development/validation, NOT production.
The production overlay requires Docker Compose 2.24.4+ (`!override` support).
For production add `backend/deploy/compose.production.yaml` after the base and
MySQL overlays, retaining the deployed project name and actual external volume
mapping. Do not apply the historical validation-volume example blindly.

```sh
docker compose --project-directory "$PWD" -f backend/deploy/compose.yaml \
  -f backend/deploy/mysql.yaml -f backend/deploy/compose.production.yaml \
  --profile mysql config --quiet
```

Before `up`, privately inspect the resolved ports: frontend must publish only on
127.0.0.1, with no backend/MySQL publication. The overlay forces APP_ENV=production,
secure cookies and disables Uvicorn proxy-header trust; APP_URL must be the
externally verified HTTPS origin and SESSION_SECRET must be random (32+ chars).
Put a locally managed TLS proxy in front of loopback frontend; verify certificate,
hostname, HTTPS login/logout and HTTP redirect before inviting users. This
conservative contract does not consume forwarded client IPs: production throttles
may group clients behind the proxy. Distributed limits and proxy-aware client-IP
policy require a separate reviewed configuration. A remote TLS proxy requires a
separate explicit network/trust review, not a wildcard trust setting.

Do not set SESSION_SECURE on the HTTP-only validation VM until TLS is provisioned.
Back up before rollout; preserve the actual MySQL volume and secrets. Do not
claim production acceptance based on config validation alone.

`compose.yaml` is the tracked source for the workspace `docker-compose.yaml`.
Run commands from the directory containing `backend/` and `frontend/`, always
passing `--project-directory "$PWD"` so relative build paths resolve correctly.

Create a private `.env` with random, URL-safe `SESSION_SECRET`, `MYSQL_PASSWORD`,
and `MYSQL_ROOT_PASSWORD`; set `APP_URL`, `FRONTEND_BIND`, `FRONTEND_PORT`, and
`SESSION_SECURE` for the deployment. The default bind is loopback for a local TLS
reverse proxy. Set an explicit LAN bind only for a trusted validation environment.
Do not reuse default passwords or publish MySQL/backend ports.

SQLite:

```sh
docker compose --project-directory "$PWD" -f backend/deploy/compose.yaml up -d --build --wait
```

MySQL (new deployment):

```sh
docker compose --project-directory "$PWD" -f backend/deploy/compose.yaml \
  -f backend/deploy/mysql.yaml --profile mysql up -d --build --wait
```

Use the MySQL runbook before importing historical data. Passwords interpolated
into the connection URL must be URL-safe. Keep the Compose project name stable:
changing it selects different volumes. Never use `down --volumes` on real data.
The MySQL overlay configures three-day binary-log retention; review backup/PITR
requirements before production use. It does not purge existing logs immediately.

Existing validation VM: do not replace its Compose file and run `up` blindly.
Its real volume is `rework_mysql_validation`, working DB `typography_restored`.
Back up the original file, explicitly map that exact external volume, preserve
the database URL, secrets and port 8080, and plan a maintenance deployment. The
QA test below uses a separate project and never mounts that volume.

The tracked `validation-vm.yaml` overlay captures that existing volume/database
mapping without secrets. During an approved maintenance deployment use all three
files (`compose.yaml`, `mysql.yaml`, `validation-vm.yaml`) with project name
`rework`. Preserve the original Compose file, set `FRONTEND_BIND=0.0.0.0` only if
LAN access is intended, and verify the resolved configuration privately before
running `up`. This overlay has been configuration-validated, not applied to the
working VM containers. Never use it for the isolated QA test.

```sh
python3 backend/scripts/compose_qa.py
```

This builds current images, creates an isolated MySQL and backend-data volume,
checks health/proxy/SPA routes and persistence across restarts/recreation, then
removes only its `typography_deployqa` containers/volumes. Results are in
`qa-results/compose/`. Do not run another QA stack on port 8082 concurrently.

VM verification on 19 November 2026 passed fresh builds, health-gated startup,
API/report/SPA proxy checks, MySQL restart persistence, container recreation
persistence, and backend restart recovery. The working stack was not restarted.