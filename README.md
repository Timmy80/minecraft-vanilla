# minecraft-vanilla
Dockerfile to run and administrate a vanilla minecraft server easily.

## Volumes
The docker image exposes 2 volumes:
  - /minecraft/server  : the main directory of the server that contains the map, the server.properties ...
  - /minecraft/backup : a backup directory for the server.

It's mandatory that you MAP the volume /minecraft/server if you want to access the MAP and the server configuration.
You can also provide your own map and server configuration in this volume, the server will use it on startup.

## Commands
This docker image allows you to administrate your minecraft server using the command `minecraft`
Here is a few example:
  - backup the map, the server.properties, and minecraft jar file: `minecraft backup`
  - give administrator rights to a player: `minecraft command "/op player-name"`
  - stop the server properly: `minecraft stop`
  - ...

## Automating
If you want to run a durable instance, you can use some options (environment variables) :
  - *DOCLEANING*=true
If you set this variable, it will automatically save your minecraft world and clean the older minecraft logfiles, and backup files.
  - *DOBACKUP*=true
If this variable is set to true, your minecraft world will be automatically backup every week.
  - *DOSTOPBACKUP*=true
If this variable is set to true, your minecraft world will be automatically backup if the container stop.

# How to build
## Using the makefile (For latest release or snapshot only)
To build the latest release of minecraft:
```bash
$ make
```
To build the latest snapshot of minecraft:
```bash
$ make latest-snapshot
```
To clean all minecraft running container and minecraft images:
```bash
$ make clean
```
You have also an help:
```bash
$ make help
```
## Using docker build (for any version of minecraft)
Example to build the snapshot 1.12-pre6 of minecraft:
```bash
$ docker build --build-arg MINECRAFT_VERSION=1.12-pre6 -t gnial/minecraft-vanilla:1.12-pre6 ./
```

# How to run

You can change default JVM : Max Heap / Min Head, with environment variables :
  - *MAXHEAP*=6144
  - *MINHEAP*=2048

To customize your server.properties instance, you can specify parameter by adding docker environment variable prefix by *MCCONF_*
The property **must be** with *underscore* instead of *dash*.
For example :
  - *MCCONF_motd*=Name of your Minecraft server
  - *MCCONF_max_players*=Number max of simultaneous players
  - *MCCONF_view_distance*=Number of max chunck view distance
  - *MCCONF_difficulty*=Difficulty level
  - *MCCONF_level_seed*=Seed of your world
  - *MCCONF_...*

To start an instance:
```bash
$ docker run -d -p 25565:25565 -v directory-to-myserver-config:/minecraft/server -v directory-to-store-backups:/minecraft/backup --name minecraft-vanilla overware/minecraft-vanilla:latest
```

If you already have a backup of your world, the container will automatically take the last backup from your backup folder and use it as your minecraft world.

To stop it, if you have enable stop backup, let the container enough time to do it before stopping:
```bash
docker stop -t 60 minecraft-vanilla
```

If you want to backup your world when your container is stopped:
```bash
$ docker run -ti --rm -v directory-to-myserver-config:/minecraft/server -v directory-to-store-backups:/minecraft/backup overware/minecraft-vanilla:latest backup
```
Otherwise, if the container is running:
```bash
$ docker exec -ti minecraft-vanilla backup
```
