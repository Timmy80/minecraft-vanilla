FROM openjdk:8-jre-slim

LABEL maintainer="Anthony THOMAS (TimmY80),Jeremy HERGAULT (reneca)" \
      description="Image that runs a Minecraft Vanilla Server. This image provides basic features like: backup, gracefull start/stop, commands, ..." \
      github="https://github.com/Timmy80/minecraft-vanilla"

ARG MINECRAFT_VERSION=latest
ARG MINECRAFT_LATEST=release

# copy the ressources for this container
COPY resources/*   /usr/local/minecraft/

RUN apt-get update && apt-get install -y \
    procps \
    wget \
    python \
    cron \
 && apt-get -y clean \
 && apt-get -y autoclean \
# add execution rights on scripts
# add the script to /usr/local/bin
# create the directories that will be mapped with on volumes
 && chmod +x /usr/local/minecraft/* \
 && ln -snf /usr/local/minecraft/minecraft.sh /usr/local/bin/minecraft \
 && ln -snf /usr/local/minecraft/rcon-client.py /usr/local/bin/rcon-client \
 && mkdir -p /minecraft/server /minecraft/backup \
# get the list of all the available versions of minecraft
 && wget -O /tmp/version_manifest.json https://launchermeta.mojang.com/mc/game/version_manifest.json \
# Download the minecraft jar file then copy the minecraft jar in /minecraft and clean the tmp
 && /usr/local/minecraft/downloadMinecraftServer.py -v $MINECRAFT_VERSION -t $MINECRAFT_LATEST \
 && cp /tmp/*.jar /minecraft/ \
 && rm -rf /tmp/*

WORKDIR /usr/local/minecraft

# expose the port, the volumes, set the entrypoint and set the command
EXPOSE 25565
VOLUME /minecraft/server /minecraft/backup

ENTRYPOINT [ "minecraft" ]

CMD [ "start" ]
