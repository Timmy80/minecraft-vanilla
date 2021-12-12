FROM openjdk:17-alpine

LABEL maintainer="Anthony THOMAS (TimmY80),Jeremy HERGAULT (reneca)" \
      description="Image that runs a Minecraft Vanilla Server. This image provides basic features like: backup, gracefull start/stop, commands, ..." \
      github="https://github.com/Timmy80/minecraft-vanilla"

ARG MINECRAFT_VERSION=latest-release

# copy the ressources for this container
COPY resources/*   /usr/local/minecraft/

RUN apk add --update-cache \
    openssh-client-default \
    python3 \
    py3-distutils-extra \
 && chmod +x /usr/local/minecraft/* \
 && ln -snf /usr/local/minecraft/minecraft.py /usr/local/bin/minecraft \
 && mkdir -p /minecraft/server /minecraft/backup /minecraft/packworld /minecraft/ssh \
 && /usr/local/minecraft/downloadMinecraftServer.py -v "$MINECRAFT_VERSION"

WORKDIR /usr/local/minecraft

# expose the port minecraft and RCON, the volumes, set the entrypoint and set the command
EXPOSE 25565 25575
VOLUME /minecraft/server /minecraft/backup

ENTRYPOINT [ "minecraft" ]

HEALTHCHECK --interval=5m --timeout=3s \
  CMD /usr/local/bin/minecraft health_status || exit 1

CMD [ "serve", "-v" ]
