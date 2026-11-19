.PHONY: up
.DEFAULT_GOAL := up

up:
	docker compose up --build
