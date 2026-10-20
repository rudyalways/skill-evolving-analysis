#!/bin/sh
set -e
ws=/opt/skill-evolver/skill_evolving_agent/workspace
if ! awk -v p="$ws" '$2 == p { found = 1 } END { exit !found }' /proc/mounts; then
  echo "mount workspace/runs/<run_id> at workspace" >&2
  exit 1
fi
exec "$@"
