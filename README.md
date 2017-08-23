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
## Using docker build (for any version of minecraft)
Example to build the snapshot 1.12-pre6 of minecraft:
```bash
$ docker build --build-arg MINECRAFT_VERSION=1.12-pre6 -t gnial/minecraft-vanilla:1.12-pre6 ./
```

# How to run

To start an instance, you can do :
```bash
$ docker run -d -p 25565:25565 -v directory-to-myserver-config:/minecraft/server -v directory-to-store-backups:/minecraft/backup --name minecraft-vanilla overware/minecraft-vanilla:latest
```

To stop it, if you have enable backup, let the container enough time to do it before stopping :
```bash
docker stop -t 60 minecraft-vanilla
```
