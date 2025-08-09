#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker/compose.yml"
NGINX_SERVICE="nginx"
NGINX_UPSTREAM_FILE="docker/nginx/upstream.conf"
TIMEOUT=30

TARGET="${1:-green}"
if [[ "$TARGET" != "green" && "$TARGET" != "blue" ]]; then
  echo "usage: $0 [green|blue]"
  exit 2
fi

if [[ "$TARGET" == "green" ]]; then
  NEW_SERVICE="app_green"
  OLD_SERVICE="app_blue"
  NEW_HOST="app_green:8000"
else
  NEW_SERVICE="app_blue"
  OLD_SERVICE="app_green"
  NEW_HOST="app_blue:8000"
fi

echo "promoting -> $NEW_SERVICE (old: $OLD_SERVICE)"
docker compose -f "$COMPOSE_FILE" up -d --no-deps "$NEW_SERVICE"

END=$((SECONDS + TIMEOUT))
while true; do
  CID=$(docker compose -f "$COMPOSE_FILE" ps -q "$NEW_SERVICE" || true)
  if [[ -n "$CID" ]]; then
    STATUS=$(docker inspect -f '{{.State.Health.Status}}' "$CID" 2>/dev/null || echo "starting")
    if [[ "$STATUS" == "healthy" ]]; then
      echo "$NEW_SERVICE is healthy"
      break
    else
      echo "Container health: $STATUS"
    fi
  fi
  if (( SECONDS >= END )); then
    echo "Timed out waiting for $NEW_SERVICE to be healthy"
    docker compose -f "$COMPOSE_FILE" logs "$NEW_SERVICE" --tail 50
    exit 3
  fi
  sleep 1
done

echo "running WebSocket smoke test from host (via nginx port)..."
if ! python - <<'PY'
import asyncio, json, sys, websockets

async def smoke():
    uri = "ws://127.0.0.1:8000/ws/chat/"
    try:
        async with websockets.connect(uri, open_timeout=3, close_timeout=3) as ws:
            await ws.send("smoke-test")
            r = await ws.recv()
            j = json.loads(r)
            if "count" in j:
                print("ws ok")
                return 0
            print("unexpected ws reply:", r)
            return 2
    except Exception as e:
        print("ws error:", e)
        return 1

sys.exit(asyncio.run(smoke()))
PY
then
  echo "WebSocket smoke FAILED — rolling back"
  docker compose -f "$COMPOSE_FILE" stop "$NEW_SERVICE" || true
  exit 4
fi

echo "updating nginx upstream to $NEW_HOST"
cat > "$NGINX_UPSTREAM_FILE" <<EOF
upstream app_upstream {
    server ${NEW_HOST};
}
EOF

echo "reloading nginx..."
if ! docker compose -f "$COMPOSE_FILE" exec -T "$NGINX_SERVICE" nginx -s reload; then
  echo "Nginx reload failed — rolling back"
  cat > "$NGINX_UPSTREAM_FILE" <<EOF
upstream app_upstream {
    server ${OLD_SERVICE}:8000;
}
EOF
  docker compose -f "$COMPOSE_FILE" exec -T "$NGINX_SERVICE" nginx -s reload || true
  docker compose -f "$COMPOSE_FILE" stop "$NEW_SERVICE" || true
  exit 5
fi

docker compose -f "$COMPOSE_FILE" stop "$OLD_SERVICE" || true
echo "promotion to $NEW_SERVICE complete."
