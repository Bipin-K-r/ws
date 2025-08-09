# for convenience, setting the commands
COMPOSE_FILE=docker/compose.yml

.PHONY: dev-up docker-up-blue docker-up-green promote-green promote-blue logs load-test

# local test
dev-up:
	uvicorn app.asgi:application --host 0.0.0.0 --port 8000 --reload

# start nginx + blue app
docker-up-blue:
	docker compose -f $(COMPOSE_FILE) up -d --build nginx app_blue

# start nginx + green app
docker-up-green:
	docker compose -f $(COMPOSE_FILE) up -d --build nginx app_green

# promote traffic to green
promote-green:
	./scripts/promote.sh green

# promote traffic to blue
promote-blue:
	./scripts/promote.sh blue

# tail logs for all services
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# run the WebSocket test script against nginx
load-test:
	python ws_load_test.py
