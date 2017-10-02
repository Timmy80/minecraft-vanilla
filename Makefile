# Makefile

LAST_IMAGE=$(shell docker images overware/minecraft-vanilla | sort | tail -1 | awk 'BEGIN{OFS=":"}{print $$1,$$2}')

.PHONY: all build latest-snapshot clean run rund

all: build ## Build by default released minecraft server docker image

build: ## Build last released minecraft server docker image
	docker build -t overware/minecraft-vanilla ./

latest-snapshot: ## Build last snapshot minecraft server docker image
	docker build --build-arg MINECRAFT_LATEST=snapshot -t overware/minecraft-vanilla:snapshot ./

clean: ## Remove running minecraft containers and minecraft images
	if docker ps -a --filter ancestor=overware/minecraft-vanilla | grep -q minecraft; then docker rm -f `docker ps -a --filter ancestor=overware/minecraft-vanilla | grep minecraft | awk '{print $$NF}'`; fi
	if docker images overware/minecraft-vanilla:latest | grep -q minecraft; then docker rmi overware/minecraft-vanilla:latest; fi
	if docker images overware/minecraft-vanilla:snapshot | grep -q minecraft; then docker rmi overware/minecraft-vanilla:snapshot; fi

run: ## Run minecraft server
	docker run -ti --rm -p 25565:25565 --name minecraft-vanilla $(LAST_IMAGE)

rund: ## Run minecraft server in daemon mode
	docker run -d -p 25565:25565 --name minecraft-vanilla $(LAST_IMAGE)

help:
	@grep -hE '(^[\.a-zA-Z_-]+:.*?##.*$$)|(^##)' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[32m%-15s\033[0m %s\n", $$1, $$2}' | sed -e 's/\[32m##/[33m/'
