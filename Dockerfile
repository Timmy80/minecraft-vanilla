FROM openjdk:17-slim

LABEL maintainer="Anthony THOMAS (TimmY80),Jeremy HERGAULT (reneca)" \
      description="Image that runs a Minecraft Vanilla Server. This image provides basic features like: backup, gracefull start/stop, commands, ..." \
      github="https://github.com/Timmy80/minecraft-vanilla"

# copy the ressources for this container
COPY resources/* /usr/local/minecraft/

RUN apt-get update && apt-get install -y --no-install-recommends -y \
    cron \
    openssh-client \
    python3 \
    python3-distutils \
    python3-jinja2 \
    curl \
 && apt-get -y clean \
 && chmod +x /usr/local/minecraft/*.sh /usr/local/minecraft/*.py \
 && ln -snf /usr/local/minecraft/entry.py /usr/local/bin/minecraft \
 && mkdir -p /minecraft/server /minecraft/backup /minecraft/packworld /minecraft/ssh \
 && curl -q https://repo1.maven.org/maven2/io/prometheus/jmx/jmx_prometheus_javaagent/0.18.0/jmx_prometheus_javaagent-0.18.0.jar -o /minecraft/jmx_prometheus_javaagent.jar \
 && mv /usr/local/minecraft/jmx_prom.yml /minecraft/

WORKDIR /usr/local/minecraft

# expose the port minecraft and RCON, the volumes, set the entrypoint and set the command
EXPOSE 8000 25565 25575
VOLUME /minecraft/server /minecraft/backup

ENTRYPOINT [ "minecraft" ]

HEALTHCHECK --interval=5m --timeout=3s \
  CMD /usr/local/bin/minecraft health_status || exit 1

CMD [ "serve", "-v", "--web-port", "8000" ]
