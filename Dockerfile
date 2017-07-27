FROM openjdk:8-jre

LABEL maintainer="Anthony THOMAS (TimmY80)" \
      description="Image that runs a Minecraft Vanilla Server. This image provides basic features like: backup, gracefull start/stop, commands, ..." \
      github="https://github.com/Timmy80/minecraft-vanilla"

ARG MINECRAFT_VERSION=latest
ARG MINECRAFT_LATEST=release

RUN apt-get update \
 && apt-get install -y \
    wget \
    python \
 && apt-get clean

# copy the ressources for this container
COPY resources/downloadMinecraftServer.py /usr/local/minecraft/
COPY resources/minecraft.sh   /usr/local/minecraft/minecraft
COPY resources/rcon-client.py /usr/local/minecraft/rcon-client

# add execution rights on scripts 
# add the script to /usr/local/bin
# create the directories that will be mapped with on volumes
RUN chmod +x /usr/local/minecraft/* \
 && cd /usr/local/bin \
 && ln -snf /usr/local/minecraft/minecraft \
 && ln -snf /usr/local/minecraft/rcon-client \
 && mkdir -p /minecraft/server /minecraft/backup

# get the list of all the available versions of minecraft
ADD https://launchermeta.mojang.com/mc/game/version_manifest.json /tmp/version_manifest.json

# Download the minecraft jar file then copy the minecraft jar in /minecraft and clean the tmp
RUN /usr/local/minecraft/downloadMinecraftServer.py -v $MINECRAFT_VERSION -t $MINECRAFT_LATEST \
 && cp /tmp/*.jar /minecraft \
 && rm -rf /tmp/*

# expose the port, the volumes, set the entrypoint and set the command
EXPOSE 25565
VOLUME /minecraft/server /minecraft/backup

ENTRYPOINT [ "minecraft" ]

CMD [ "start" ]

