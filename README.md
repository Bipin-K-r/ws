# WS – Django ASGI WebSocket Service

- **WebSocket endpoint** `/ws/chat/` — counts messages per connection
- **HTTP endpoints**:
  - `/health` (liveness)
  - `/ready` (readiness)
  - `/metrics`
- **Graceful shutdown** (closes sockets with code 1001 within 10s)
- **Blue/Green deployment**
- **Promotion script** to flip traffic between colors after smoke tests


# makefile commands
- *make dev-up*
- *make docker-up-blue*
- *make promote-green*
- *make promote-blue*
- *make logs*
- *make load-test*


# for smoke test
- **run from root** 
- docker compose -f docker/compose.yml up -d --build nginx app_blue
- ./scripts/promote.sh green -> promotion to greem
- ./scripts/promote.sh blue -> promotion to blue
# check for errors if any with logs


