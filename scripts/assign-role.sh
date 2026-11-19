#!/usr/bin/env bash
# Operator-only helper. Run on the Docker host; never expose via HTTP.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
if [[ $# -ne 2 ]]; then
  echo "Usage: bash backend/scripts/assign-role.sh EMAIL_OR_id:N 'ROLE_TITLE_OR_id:N'" >&2
  exit 2
fi
# Explicit files avoid choosing a different database through a Compose override.
COMPOSE=(docker compose --project-directory "$ROOT" -f "$ROOT/docker-compose.yaml")
if [[ -f "$ROOT/compose.mysql.yaml" ]]; then
  COMPOSE+=(-f "$ROOT/compose.mysql.yaml")
  COMPOSE+=(--profile mysql)
fi
"${COMPOSE[@]}" exec -T backend .venv/bin/python -m app.assign_role "$1" "$2" < /dev/null
read -r -p 'Apply this role assignment? Type YES: ' confirmation
[[ "$confirmation" == YES ]] || { echo 'Cancelled'; exit 1; }
"${COMPOSE[@]}" exec -T backend .venv/bin/python -m app.assign_role "$1" "$2" --apply
echo 'Re-login/refresh navigation. To revert, assign the previous role ID shown above.'