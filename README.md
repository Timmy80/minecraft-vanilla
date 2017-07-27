# minecraft-vanilla
Dockerfile to run and administrate a vanilla minecraft server easily.

## volumes
The docker image exposes 2 volumes:
  - /minecraft/server  : the main directory of the server that contains the map, the server.properties ...
  - /minecraft/backup : a backup directory for the server.
  
It's mandatory that you MAP the volume /minecraft/server if you want to access the MAP and the server configuration.
You can also provite your hown map and server configuration in this volume, the server will use it on startup.

## Commands
This docker image allows you to administrate your minecraft server using the command `minecraft`
Here is a few example:
  - backup the map, the server.properties, and minecraft jar file: `minecraft backup`
  - give adminstrator rights to a player: `minecraft command "/op player-name"`
  - stop the server properly: `minecraft stop`
  - ...

# How to build
## Using the makefile (For latest release or snapshot only)
To build the latest release of minecraft:
```sh
$ make
```
To build the latest snapshot of minecraft:
```sh
$ make latest-snapshot
```
## Using docker build (for any version of minecraft)
Example to build the snapshot 1.12-pre6 of minecraft:
```sh
$ docker build --build-arg MINECRAFT_VERSION=1.12-pre6 -t gnial/minecraft-vanilla:1.12-pre6 ./
```
