#!/bin/bash

jarfile=$(cd /minecraft && files=(minecraft_server*.jar) && echo "${files[0]}")

SERVICE="/minecraft/$jarfile"
SCREENNAME='minecraft'
OPTIONS='nogui'
WORLD='minecraft-world'
MCPATH='/minecraft/server'
BACKUPPATH='/minecraft/backup/'
MAXHEAP=4096
MINHEAP=1024
HISTORY=1024
CPU_COUNT=3
RCON_PORT=25566
RCON_PASSWD=rcon-passwd
INVOCATION="java -Xmx${MAXHEAP}M -Xms${MINHEAP}M -XX:+UseConcMarkSweepGC \
-XX:+CMSIncrementalPacing -XX:ParallelGCThreads=$CPU_COUNT -XX:+AggressiveOpts \
-jar $SERVICE $OPTIONS"

get_property() {
    res=$(grep "$1" $MCPATH/server.properties)
    if [ -z "$res" ]; then
	return 1
    fi

    cut -d "=" -f 2 <<< "$res"
}

set_property() {
    res=$(grep "$1" $MCPATH/server.properties)
    if [ -z "$res"]; then
        echo "$1=$2" >> $MCPATH/server.properties
    else
        sed -i.bak "s/$res/$1=$2/g" $MCPATH/server.properties
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
    echo "Starting $SERVICE..."
    cd $MCPATH
    $INVOCATION &
    wait $!

    #accept eula and restart if necessary
    if [ -n "$(tail logs/latest.log | grep "EULA")" ]; then
        sed -i.bak s/eula=false/eula=true/g eula.txt
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
  if [ "$DOBACKUP" == "true" ]; then
    mc_backup
  fi
}

mc_backup() {
   mc_saveoff

   NOW=`date "+%Y-%m-%d_%Hh%M"`
   BACKUP_FILE="$BACKUPPATH/${WORLD}_${NOW}.tar"

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
   bzip2 -f "$BACKUP_FILE"
   echo "Done."
}

mc_command() {
  command="$1";
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
    WORLD=$(get_property level-name)
    RCON_PORT=$(get_property rcon.port)
    if [ -z "$RCON_PORT" ]; then
        echo "adding rcon.port value 25575"
        set_property rcon.port 25575
    fi

    RCON_PASSWD=$(get_property rcon.password)
    if [ -z "$RCON_PASSWD" ]; then
        echo "adding rcon.password value rcon-passwd"
        set_property rcon.password rcon-passwd
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
    else
      echo "$SERVICE is not running."
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
  echo "Usage: $0 {start|stop|backup|status|command \"server command\"}"
  exit 1
  ;;
esac

exit 0

#end of script
