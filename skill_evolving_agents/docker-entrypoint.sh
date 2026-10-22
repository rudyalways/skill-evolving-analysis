#!/bin/sh
set -e
root=/opt/skill-evolver/skill_evolving_agents
ws=$root/workspace
if ! awk -v p="$ws" '$2 == p { found = 1 } END { exit !found }' /proc/mounts; then
  echo "mount workspace/runs/<run_id> at workspace" >&2
  exit 1
fi
if [ ! -f "$root/AGENT.md" ]; then
  echo "mount the selected agent brief at AGENT.md" >&2
  exit 1
fi
if [ -z "${STAGE_DIR:-}" ] || [ ! -d "$root/$STAGE_DIR" ]; then
  echo "set STAGE_DIR and mount the selected stage directory" >&2
  exit 1
fi
exec "$@"
