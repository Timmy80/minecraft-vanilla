all: build

build: 
	docker build -t overware/minecraft-vanilla ./

latest-snapshot:
	docker build --build-arg MINECRAFT_LATEST=snapshot -t oveware/minecraft-vanilla:snapshot ./

