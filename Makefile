# Makefile

REPO=overware
LAST_IMAGE=$(shell docker images ${REPO}/minecraft-vanilla | sort | tail -1 | awk 'BEGIN{OFS=":"}{print $$1,$$2}')

.PHONY: all build push latest-snapshot push-snapshot clean run rund help

all: build ## Build by default latest docker images

build: ## Build latest docker image
	docker build -t ${REPO}/minecraft-vanilla .

push: ## Build and push multi-architecture last released minecraft server docker image
	docker buildx build --platform linux/amd64,linux/arm64/v8 -t ${REPO}/minecraft-vanilla --push .

develop: ## Build last development docker image
	docker build -t ${REPO}/minecraft-vanilla:develop ./

push-develop: ## Build and push multi-architecture last development docker image
	docker buildx build --platform linux/amd64,linux/arm64/v8 -t ${REPO}/minecraft-vanilla:develop --push .

clean: ## Remove running minecraft containers and minecraft images
	if docker ps -a --filter ancestor=${REPO}/minecraft-vanilla | grep -q minecraft; then docker rm -f `docker ps -a --filter ancestor=${REPO}/minecraft-vanilla | grep minecraft | awk '{print $$NF}'`; fi
	if docker images ${REPO}/minecraft-vanilla:latest | grep -q minecraft; then docker rmi ${REPO}/minecraft-vanilla:latest; fi
	if docker images ${REPO}/minecraft-vanilla:develop | grep -q minecraft; then docker rmi ${REPO}/minecraft-vanilla:develop; fi

run: ## Run minecraft server
	docker run -ti --rm -p 8000:8000 -p 25565:25565 --name minecraft-vanilla ${LAST_IMAGE}

rund: ## Run minecraft server in daemon mode
	docker run -d -p 8000:8000 -p 25565:25565 --name minecraft-vanilla ${LAST_IMAGE}

help:
	@grep -hE '(^[\.a-zA-Z_-]+:.*?##.*$$)|(^##)' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[32m%-15s\033[0m %s\n", $$1, $$2}' | sed -e 's/\[32m##/[33m/'
