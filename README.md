# minecraft-vanilla
Dockerfile to run and administrate a vanilla Minecraft server easily.

## Volumes
The docker image exposes 3 volumes:
  - /minecraft/server  : the main directory of the server that contains the map, the server.properties ...
  - /minecraft/backup : a backup directory for the server.
  - /minecraft/ssh : a directory where to place your id_rsa and id_rsa.pub in order to store your backup remotely.

It's mandatory that you MAP the volume /minecraft/server if you want to access the MAP and the server configuration.
You can also provide your own map and server configuration in this volume, the server will use it on startup.

## Commands
This docker image allows you to administrate your Minecraft server using the command `minecraft`
Here is a few example:
  - backup the map and the server.properties: `minecraft backup`
  - give administrator rights to a player: `minecraft command op player-name`
  - stop the server properly: `minecraft stop`
  - get a property of the Minecraft server: `minecraft property level-name`
  - change a property of the Minecraft server: `minecraft property view-distance 15`
  - get a configuration of this wrapper: `minecraft config min-heap`
  - change a configuration of this wrapper: `minecraft config max-heap 8192`
  - change the version of Minecraft: `minecraft set-version 20w17a` or with **fabric-** prefix for a fabric server `minecraft set-version fabric-1.18.2`
  - ...

All these commands can be sent remotely using the **RCON protocol** on the port **25575** (See [Remote management](#remote-management))

## Automating

If you want to run a durable instance, you can configure the **auto-clean** feature:
  - add the option `--auto-clean` to the command line or set the env `MC_AUTO_CLEAN=true` to enable it. (the old variable DOCLEANING still works)
  - when **auto-clean** is enabled a cleanup is performed daily and keeps 20 days of logs + 40 days of backups (acts on local backups only)

If you want to backup your world frequently you can configure the **auto-backup** feature:
  - add the option `--auto-backup` to the command line or set the env `MC_AUTO_BACKUP=true` to enable it. (the old variable DOBACKUP still works)
  - when **auto-backup** is configured the map is backed-up weekly (by default) using cron. A backup is also performed each time the server is stopped.
  - if you want to change the backup frequency then add the option `--backup-frequency` to the command line or set the env **MC_BACKUP_FREQUENCY**. example: `MC_BACKUP_FREQUENCY=daily`.

If you would like to run a Minecraft server on temporary cloud instance instead of permanently running server you can use the **auto-dowload** and/or **auto-upload**.  
It requires to configure the ssh-remote-url and add a ssh key to the container.
  - to configure it add the option `--ssh-remote-url` to the command line or set the env `MC_SSH_REMOTE_URL` with a value of the form `user@server:/path/to/backup/dir`
  - map a volume with and **id_rsa** and **id_rsa.pub** file on **/minecraft/ssh**. (use the following command to create the ssh key if you dont have one: `ssh-keygen -b 4096 -
t rsa -f ./id_rsa`)

**auto-dowload** feature :
  - add the option `--auto-dowload` to the command line or set the env `MC_AUTO_DOWNLOAD=true` to enable it.
  - when **auto-dowload** is configured the server looks for the latest backup on the remote server. If the latest backup is not available localy then it downloads it.

**auto-upload** feature :
  - add the option `--auto-upload` to the command line or set the env `MC_AUTO_UPLOAD=true` to enable it.
  - when **auto-upload** is configured, each time server performs a backup the file is uploaded on the remote.

## Remote management

This image contains a RCON server that allows you to send it commands remotely like on the RCON port of the Minecraft server.  
If your RCON command starts with `minecraft` then it will interpreted by this server like one of any command you could use inside of this image.  
Any other command will be forwarded to the Minecraft server if it's running.

# How to build
## Using the makefile (For latest release or snapshot only)
To build the latest release of Minecraft:
```bash
$ make
```
The makefile can be use with a different repository name:
```bash
$ make [target] -e REPO=overware
```
To push the latest release of Minecraft for [multi-arch](https://docs.docker.com/desktop/multi-arch/):
```bash
$ make push
```
To build the latest snapshot of Minecraft:
```bash
$ make latest-snapshot
```
To push the latest snapshot of Minecraft for [multi-arch](https://docs.docker.com/desktop/multi-arch/):
```bash
$ make push-snapshot
```
To clean all Minecraft running container and Minecraft images:
```bash
$ make clean
```
You have also an help:
```bash
$ make help
```
## Using docker build (for any version of Minecraft)
Example to build the snapshot 1.12-pre6 of Minecraft:
```bash
$ docker build --build-arg MINECRAFT_VERSION=1.12-pre6 -t overware/minecraft-vanilla:1.12-pre6 ./
```

# How to run

You can change default JVM : Max Heap / Min Head, with environment variables :
  - *MC_MAX_HEAP*=6144 (*MAXHEAP* also works)
  - *MC_MIN_HEAP*=2048 (*MINHEAP* also works)

To customize your server.properties instance, you can specify parameter by adding docker environment variable prefix by *MCCONF_*.
For example :
  - *MCCONF_motd*=Name of your Minecraft server
  - *MCCONF_max-players*=Number max of simultaneous players
  - *MCCONF_view-distance*=Number of max chunck view distance
  - *MCCONF_difficulty*=Difficulty level
  - *MCCONF_level-seed*=Seed of your world
  - *MCCONF_...*

To start an instance:
```bash
$ docker run -d -p 25565:25565 -v directory-to-myserver-config:/minecraft/server -v directory-to-store-backups:/minecraft/backup --name minecraft-vanilla overware/minecraft-vanilla:latest
```

If you already have a backup of your world in **/minecraft/backup** and no world in **/minecraft/server**, the container will automatically take the last backup from your backup folder and use it as your Minecraft world.

To stop it, if you have enabled **auto-backup**, let the container enough time to do it before stopping:
```bash
docker stop -t 60 minecraft-vanilla
```

If you want to manually backup your world:
```bash
$ docker exec -ti minecraft-vanilla backup
```

## using docker-compose

This and example of docker compose configuration:

```yml
version: "3"
services:
    minecraft-vanilla:
        image: overware/minecraft-vanilla:1.15.2
        ports:
          - "25565:25565"
          - "25575:25575"
        environment:
          - MC_AUTO_CLEAN=True
          - MC_AUTO_BACKUP=True
          - MCCONF_motd=Localhost Minecraft Test Server
          - MCCONF_level-name=test-world
          #- MC_AUTO_DOWNLOAD=True
          #- MC_AUTO_UPLOAD=True
          #- MC_SSH_REMOTE_URL=user@server:/path/to/backup/dir
        #volumes:
        #  - "./ssh/:/minecraft/ssh/:ro"
        command:
          serve -v --backup-frequency daily

```
