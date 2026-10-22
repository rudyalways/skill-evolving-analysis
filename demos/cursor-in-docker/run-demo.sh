#!/bin/sh
# Build a Linux image with the Cursor agent CLI, start one container, and
# show why mounting the macOS CLI does not log that container in.
set -eu

cd "$(dirname "$0")"
image=cursor-cli-demo
name=cursor-cli-demo
host_agent="${HOME}/.local/share/cursor-agent"

docker build -t "$image" .

echo
echo "== Linux CLI installed in the image =="
docker run --rm "$image" agent --version

echo
echo "== Mounting the macOS CLI into the same Linux image =="
if [ ! -d "$host_agent" ]; then
  echo "no host CLI at $host_agent"
else
  docker run --rm \
    -v "$host_agent:/host-cursor-agent:ro" \
    --entrypoint bash \
    "$image" \
    -lc '
      bin=$(find /host-cursor-agent/versions -type f -name node | head -1)
      echo "mounted node: $bin"
      if "$bin" --version; then
        echo "unexpected: the macOS node binary ran"
      else
        echo "macOS node exit=$?"
      fi
    '
fi

echo
echo "== Container left running as $name =="
docker rm -f "$name" >/dev/null 2>&1 || true
auth_args=""
if [ -n "${CURSOR_API_KEY:-}" ]; then
  auth_args="-e CURSOR_API_KEY"
fi
# shellcheck disable=SC2086
docker run -d --name "$name" $auth_args "$image" >/dev/null
docker exec "$name" agent status || true

cat <<EOF

Next, from this directory:

  docker exec -it $name bash

Inside the container, either:

  NO_OPEN_BROWSER=1 agent login
  # open the printed URL in the Mac browser; the login is stored in the
  # container at /root/.config/cursor/auth.json

or start the container with a user API key from cursor.com/dashboard:

  docker rm -f $name
  docker run -d --name $name -e CURSOR_API_KEY "\$CURSOR_API_KEY" $image
  docker exec $name agent status

The key is read from the environment. Do not pass it as a literal in CMD,
and do not bake it into the image.
EOF
