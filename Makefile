# Makefile

REPO=overware
LAST_IMAGE=`shell docker images ${REPO}/minecraft-vanilla | sort | tail -1 | awk 'BEGIN{OFS=":"}{print $$1,$$2}'`

.PHONY: all build push latest-snapshot push-snapshot clean run rund help

all: build ## Build by default released minecraft server docker image

build: ## Build last released minecraft server docker image
	docker build -t $(REPO)/minecraft-vanilla .

push: ## Build and push multi-architecture last released minecraft server docker image
	docker buildx build --platform linux/amd64,linux/arm64/v8 -t $(REPO)/minecraft-vanilla --push .

latest-snapshot: ## Build last snapshot minecraft server docker image
	docker build --build-arg MINECRAFT_VERSION=latest-snapshot -t $(REPO)/minecraft-vanilla:snapshot ./

push-snapshot: ## Build and push multi-architecture last snapshot minecraft server docker image
	docker buildx build --platform linux/amd64,linux/arm64/v8 -t $(REPO)/minecraft-vanilla --push .

clean: ## Remove running minecraft containers and minecraft images
	if docker ps -a --filter ancestor=${REPO}/minecraft-vanilla | grep -q minecraft; then docker rm -f `docker ps -a --filter ancestor=${REPO}/minecraft-vanilla | grep minecraft | awk '{print $$NF}'`; fi
	if docker images ${REPO}/minecraft-vanilla:latest | grep -q minecraft; then docker rmi ${REPO}/minecraft-vanilla:latest; fi
	if docker images ${REPO}/minecraft-vanilla:snapshot | grep -q minecraft; then docker rmi ${REPO}/minecraft-vanilla:snapshot; fi

run: ## Run minecraft server
	docker run -ti --rm -p 25565:25565 --name minecraft-vanilla $(LAST_IMAGE)

rund: ## Run minecraft server in daemon mode
	docker run -d -p 25565:25565 --name minecraft-vanilla $(LAST_IMAGE)

help:
	@grep -hE '(^[\.a-zA-Z_-]+:.*?##.*$$)|(^##)' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[32m%-15s\033[0m %s\n", $$1, $$2}' | sed -e 's/\[32m##/[33m/'
