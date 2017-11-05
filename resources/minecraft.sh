#!/bin/bash

jarfile=$(cd /minecraft && files=(minecraft_server*.jar) && echo "${files[0]}")

SERVICE="/minecraft/$jarfile"
SCREENNAME='minecraft'
OPTIONS='nogui'
WORLD=`cat /minecraft/server/server.properties 2> /dev/null | grep level-name | cut -d= -f2 || echo world`
MCPATH='/minecraft/server'
BACKUPPATH='/minecraft/backup'
MAXHEAP=${MAXHEAP:-6144}
MINHEAP=${MINHEAP:-2048}
CPU_COUNT=3
RCON_PORT=25566
RCON_PASSWD=rcon-passwd
INVOCATION="java -Xmx${MAXHEAP}M -Xms${MINHEAP}M \
-XX:ParallelGCThreads=$CPU_COUNT -XX:+AggressiveOpts \
-jar $SERVICE $OPTIONS"

get_property() {
  local res=$(grep "$1" $MCPATH/server.properties)
  if [ -z "$res" ]; then
    return 1
  fi

  cut -d "=" -f 2 <<< "$res"
}

set_property() {
  local propertyName=$1
  shift
  local res=$(grep "$propertyName" $MCPATH/server.properties)
  if [ -z "$res"]; then
    echo "$propertyName=$@" >> $MCPATH/server.properties
  else
    sed -i "s/$res/$propertyName=$@/g" $MCPATH/server.properties
  fi
}

as_rcon() {
  rcon-client -t 127.0.0.1:$RCON_PORT -p $RCON_PASSWD $@
}

cron_init() {
  # Execute cleaning everyday
  if [ "$DOCLEANING" == "true" ]; then
    cp /usr/local/minecraft/cleaning.sh /etc/cron.daily/cleaning.sh
  fi

  # Backup minecraft world every week
  if [ "$DOBACKUP" == "true" ]; then
    cp /usr/local/minecraft/backup.sh /etc/cron.weekly/backup.sh
  fi

  # Run cron if needed
  if [ "$DOCLEANING" == "true" ] || [ "$DOBACKUP" == "true" ]; then
    echo "Init crontab"
    cron
  fi
}

mc_start() {
  if  pgrep -f $SERVICE > /dev/null
  then
    echo "$SERVICE is already running!"
  else
    if ! [ -f /minecraft/server/eula.txt ]; then
      # First time the server start - Look into backup for a Map
      LAST_WORLD=`basename $(ls $BACKUPPATH/*.tar.gz 2> /dev/null | sort | tail -1) 2> /dev/null`
      if [ -n "$LAST_WORLD" ]; then
        NAME=`echo -e "$LAST_WORLD" | cut -f1 -d.`
        WORLD=`echo -e "$NAME" | cut -f1 -d_`
        WORLD_DATE=`echo -e "$NAME" | cut -f2-3 -d_`

        echo -e "Importing world $WORLD [ $WORLD_DATE ]"
        tar zxf $BACKUPPATH/$LAST_WORLD -C /tmp/
        mv /tmp/$WORLD /minecraft/server/
        rm -rf /tmp/*.jar
      fi
    fi

    # Set MC properties
    IFS=$'\t\n'
    for property in $(printenv | grep "^MCCONF_" | sed 's/^MCCONF_//g')
    do
      propertyKey=`echo -e $property | cut -d "=" -f 1 | sed 's/_/-/g' | tr '[A-Z]' '[a-z]'`
      propertyValue=`echo -e $property | cut -d "=" -f 2`
      set_property "$propertyKey" "$propertyValue"
    done
    IFS=$' \t\n'

    echo "Starting $SERVICE..."
    cd $MCPATH
    $INVOCATION &
    wait $!

    #accept eula and restart if necessary
    if [ -n "$(tail logs/latest.log | grep EULA)" ]; then
        sed -i s/eula=false/eula=true/g eula.txt

        # Change world name if it's load from backup
        if [ "$WORLD" != "world" ]; then
          set_property level-name "$WORLD"
        fi

        $INVOCATION &
        wait $!
    fi
  fi
}

mc_saveoff() {
  if pgrep -f $SERVICE > /dev/null
  then
    echo "$SERVICE is running... suspending saves"
    as_rcon say SERVER BACKUP STARTING. Server going readonly...
    as_rcon save-off
    as_rcon save-all
    sync
    sleep 10
  else
    echo "$SERVICE is not running. Not suspending saves."
  fi
}

mc_saveon() {
  if pgrep -f $SERVICE > /dev/null
  then
    echo "$SERVICE is running... re-enabling saves"
    as_rcon save-on
    as_rcon say SERVER BACKUP ENDED. Server going read-write...
  else
    echo "$SERVICE is not running. Not resuming saves."
  fi
}

mc_stop() {
  if pgrep -f $SERVICE > /dev/null
  then
    echo "Stopping $SERVICE"
    as_rcon say SERVER SHUTTING DOWN IN 5 SECONDS. Saving map...
    as_rcon save-all
    as_rcon stop
  else
    echo "$SERVICE was not running."
  fi

  # Backup before container stop (if enable)
  if [ "$DOSTOPBACKUP" == "true" ]; then
    mc_backup
  fi
}

mc_backup() {
   mc_saveoff

   local BACKUP_FILE="$BACKUPPATH/${WORLD}_$(date '+%Y-%m-%d_%Hh%M').tar"

   echo "Backing up minecraft configuration..."
   tar -C "$MCPATH" -cf "$BACKUP_FILE" server.properties

   echo "Backing up minecraft world..."
   for dimension in $MCPATH/$WORLD*; do
      tar -C "$MCPATH" -rf "$BACKUP_FILE" $(basename $dimension)
   done

   echo "Backing up $SERVICE"
   tar -C "$MCPATH" -rf "$BACKUP_FILE" $SERVICE

   mc_saveon

   echo "Compressing backup..."
   gzip -f "$BACKUP_FILE"
   echo "Done."
}

mc_command() {
  local command="$1";
  if pgrep -f $SERVICE > /dev/null
  then
    echo "$SERVICE is running... executing command"
    as_rcon $command
  fi
}

#read server.properties to get the following informations
# WORLD ?
# RCON_PORT ?
# RCON_PASSWD ?

if [ -f $MCPATH/server.properties ]; then
    RCON_PORT=$(get_property rcon.port)
    if [ -z "$RCON_PORT" ]; then
        echo "adding rcon.port value 25575"
        set_property rcon.port 25575
    fi

    RCON_PASSWD=$(get_property rcon.password)
    if [ -z "$RCON_PASSWD" ]; then
        RCON_PASSWD=`date +%s | sha256sum | base64 | head -c 32`
        echo "adding rcon.password value $RCON_PASSWD"
        set_property rcon.password "$RCON_PASSWD"
    fi

    RCON_BROADCAST=$(get_property broadcast-rcon-to-ops)
    if [ -z "$RCON_BROADCAST" ]; then
        echo "adding broadcast-rcon-to-ops value true"
        set_property broadcast-rcon-to-ops true
    fi

    RCON_ENABLE=$(get_property enable-rcon)
    if [ -z "$RCON_ENABLE" ]; then
        echo "adding enable-rcon value true"
        set_property enable-rcon true
    elif [[ "$RCON_ENABLE" == "false"  ]]; then
        echo "updating enable-rcon to true"
        set_property enable-rcon true
    fi
else
    touch $MCPATH/server.properties
    set_property rcon.port 25575
    set_property rcon.password rcon-passwd
    set_property broadcast-rcon-to-ops true
    set_property enable-rcon true
fi

# trap sigterm from docker daemon to stop server gracefully
trap 'mc_stop && exit 0' SIGTERM

#Start-Stop here
case "$1" in
  start)
    # Start cron for cleaning and backup (if enable)
    cron_init
    # Start minecraft server
    mc_start
    ;;
  stop)
    mc_stop
    ;;
  backup)
    mc_backup
    ;;
  status)
    if pgrep -f $SERVICE > /dev/null
    then
      echo "$SERVICE is running."
      exit 0
    else
      echo "$SERVICE is not running."
      exit 1
    fi
    ;;
  unpack_world)

    ;;
  rcon_password)
    echo -e "$RCON_PASSWD"
    exit 0
    ;;
  health_status)
    if [[ $(as_rcon list) =~ "players online" ]]; then
      exit 0
    else
      exit 1
    fi
    ;;
  command)
    if [ $# -gt 1 ]; then
      shift
      mc_command "$*"
    else
      echo "Must specify server command (try 'help'?)"
    fi
    ;;

  *)
  echo "Usage: $0 {start|stop|backup|status|rcon_password|command \"server command\"}"
  exit 1
  ;;
esac

exit 0

#end of script
