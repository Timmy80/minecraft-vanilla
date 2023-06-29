import threading
import subprocess
import logging
import rcon
import os.path
import copy
import time
import tarfile
import gzip
import shutil
import sys
import traceback
from enum import Enum

class PropertiesFile:

    def __init__(self, path):
        self.path = path
        self.properties = {}
        self.read()

    def read(self) :
        if os.path.isfile(self.path):
            with open(self.path, "r") as file:
                for line in file:
                    line = line.strip()
                    if line.startswith("#") == False :
                        parts = line.split('=')
                        if len(parts) != 2 or parts[0] == "":
                            continue
                        self.properties[parts[0]] = parts[1]

    def write(self):
        with open(self.path, "w") as file:
            for key in self.properties:
                file.write(str.format("{}={}\n", key, self.properties[key]))

    def isEmpty(self):
        return not bool(self.properties)

    def setProperty(self, property, value):
        if property == None or property.strip() == "":
            return False

        self.properties[property] = value
        return True

    def getProperty(self, property):
        return self.properties[property]

    def populateProperties(self):
        """
        Read the properties file and read the environment to look for the properties to add to server.properties.
        Those properties are prefixed by 'MCCONF_'.
        This also defines the mandatory properties required to enable RON.
        This method does not perform a write. if you want the change to be taken into account you MUST call it youself.
        """
        self.read()
        self.setProperty("rcon.port", "27015")
        self.setProperty("rcon.password", "rcon-passwd")
        self.setProperty("broadcast-rcon-to-ops", "true")
        self.setProperty("enable-rcon", "true")
        self.setProperty("enable-jmx-monitoring", "true")

        for config in [ var for var in os.environ if var.startswith("MCCONF") ]:
            value = os.environ.get(config)
            self.setProperty(config[7:], value)


class InternalError(Exception):
    """For internal error management"""

    def __init__(self, *args):
        if args :
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return 'Error: {0}'.format(self.message)
        else:
            return 'Internal error'

class MinecraftStatus(Enum):
    UNAVAILABLE = 0
    STOPPED = 1
    STARTED = 2
    SAVING = 3
    UPLOADING = 4
    DOWNLOADING = 5
    LOADING = 6

def ignorelogs(tarinfo):
    """
    function to exclude the logs from the backups
    """
    if tarinfo.name.startswith("logs"):
        return None
    return tarinfo

class MinecraftServer:

    def __init__(self, args):
        self.thread = None
        self.args = args
        self.properties = PropertiesFile(os.path.join(self.args.workdir, "server.properties"))
        self.status = MinecraftStatus.STOPPED
        self._lock = threading.Lock()
        self.jvm = None

    def run(self):
        try:
            """Start the JVM"""
            logging.info("Server is starting")

            if self.args.auto_download :
                with self._lock:
                    self.status = MinecraftStatus.DOWNLOADING
                self._download()
            # if auto-download of the workdir is empty
            if self.args.auto_download or not os.listdir(self.args.workdir):
                with self._lock:
                    self.status = MinecraftStatus.LOADING
                self._load()

            # First lets create the eula.txt file if needed
            workPath = os.path.abspath(self.args.workdir)
            eulaPath = os.path.join(workPath, "eula.txt")
            if os.path.isfile(eulaPath) == False:
                with open(eulaPath, "w") as eula:
                    eula.write("eula=true\n")

            # Then create or update the server.properties
            self._populateProperties()

            # Then we can build the java command and run it a subprocess
            command = ["java"]
            command.append(str.format("-Xmx{MAXHEAP}M", MAXHEAP=self.args.max_heap))
            command.append(str.format("-Xms{MINHEAP}M", MINHEAP=self.args.min_heap))
            command.append("-javaagent:/minecraft/jmx_prometheus_javaagent.jar=9000:/minecraft/jmx_prom.yml")
            if not self.args.use_gfirst:
                command.append(str.format("-XX:ParallelGCThreads={CPU_COUNT}", CPU_COUNT=self.args.gc_threads)) 
            else:
                command.append("-XX:+UseG1GC")
            command.append("-jar")
            command.append(self.args.jar)
            command.append(self.args.opt)
            logging.info(str(command))
            with self._lock:
                self.jvm = subprocess.Popen(command, cwd=workPath)
            with self._lock:
                self.status = MinecraftStatus.STARTED
            self.jvm.wait()

            if self.args.auto_backup or self.args.auto_upload:
                with self._lock:
                    self.status = MinecraftStatus.SAVING
                backup = self._backup()
            if self.args.auto_upload :
                with self._lock:
                    self.status = MinecraftStatus.UPLOADING
                self._upload(backup)

        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            respStr= str.format("Error: exception cautgh. {}", traceback.format_exception(exc_type, exc_value, exc_traceback)[-1])
            logging.exception(exc_type)

        finally:
            with self._lock:
                self.status = MinecraftStatus.STOPPED
            self.jvm = None
            logging.info("Server is stopped")

    def _download(self):
        """
        Download the latest backup from the remote server
        """
        urlParts = self.args.ssh_remote_url.split(":")
        userHost = urlParts[0]
        remotePath = urlParts[1]
        sshCmd = ["ssh", "-o", "StrictHostKeyChecking=no", userHost, "ls -t {0}/*.tar.gz | head -n 1".format(remotePath)]
        logging.info("Looking for latest backup: %s", sshCmd)
        res = subprocess.check_output(sshCmd)
        lastbackup = res.decode("utf-8").strip()
        if lastbackup == "":
            logging.info("No backup available on remote server.")
            return False

        logging.info("latest backup is: %s", lastbackup)
        filepath = os.path.join(self.args.backup_dir, str(lastbackup))
        if os.path.isfile(filepath):
            logging.info("latest backup %s is already available locally", lastbackup)
        else:
            scpCmd = ["scp", "-o", "StrictHostKeyChecking=no", "{0}:{1}".format(userHost, os.path.join(remotePath, lastbackup)), self.args.backup_dir]
            logging.info("downloading the latest backup")
            res = subprocess.check_output(scpCmd)
            logging.debug("Server response: %s", res)

    def _load(self):
        """
        Load the latest local backup to the run directory.
        """
        backups = os.listdir(self.args.backup_dir)
        if not backups:
            logging.info("No backup available localy")
            return False

        backups.sort()
        lastbackup = backups[-1]
        logging.info("Latest local backup is: %s", lastbackup)
        filepath = os.path.join(self.args.backup_dir, lastbackup)

        logging.info("cleaning previous server working dir %s", self.args.workdir)
        for torm in [ os.path.join(self.args.workdir, f) for f in os.listdir(self.args.workdir)]:
            if os.path.isfile(torm):
                os.remove(torm)
            else:
                shutil.rmtree(torm)

        logging.info("Extracting backup %s to %s", filepath, self.args.workdir)
        with tarfile.open(name=filepath, mode='r:gz') as tar :
            tar.extractall(path=self.args.workdir)

    def _backup(self):
        logging.info("cleaning old backups")
        for filename in os.listdir(self.args.backup_dir):
            fullpath = os.path.join(self.args.backup_dir,filename)
            logging.info("Removing backup: %s", fullpath)
            os.remove(fullpath)

        logging.info("backuping world")
        res = []
        try:
            # first we save the world and avoid the server from writting the map during the compression
            self.asRcon("say SERVER BACKUP STARTING. Server going readonly...")
            res.append(self.asRcon("save-off"))
            res.append(self.asRcon("save-all"))
        except:
            pass

        self.properties.read()
        tarName = "{0}_{1}.tar".format(self.properties.getProperty("level-name"), time.strftime("%Y-%m-%d_%Hh%M", time.gmtime()))
        tarFile = os.path.join(self.args.backup_dir, tarName)
        with tarfile.open(name=tarFile, mode='w') as tar :
            tar.add(self.args.workdir, arcname="/", filter=ignorelogs)

        try:
            # re-enable the server ability to write the map
            res.append(self.asRcon("save-on"))
            self.asRcon("say SERVER BACKUP ENDED. Server going read-write...")
        except:
            pass

        with open(tarFile, 'rb') as f_in:
            with gzip.open('{0}.gz'.format(tarFile), 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        backupFile = "{0}.gz".format(tarName)

        os.remove(tarFile)

        return { "log": res, "file" : backupFile }

    def _upload(self, backup):
        scpCmd = ["scp", "-o", "StrictHostKeyChecking=no", os.path.join(self.args.backup_dir, backup["file"]), self.args.ssh_remote_url]
        logging.info("uploading world: %s", scpCmd)
        res = subprocess.check_output(scpCmd)

    def start(self):
        if self.thread and self.thread.is_alive():
            raise InternalError("Server is already running")
        self.thread = threading.Thread(target=self.run, args=())
        self.thread.start()

    def stop(self):
        """
        Gracefully stop the JVM
        Throws an error if the server was not running
        """
        if not self.isRunning():
            raise InternalError("Server was not running")

        res = []
        try:
            self.asRcon("say SERVER SHUTTING DOWN IN 5 SECONDS. Saving map...")
            res.append(self.asRcon("save-all"))
            res.append(self.asRcon("stop"))
        except:
            self.kill()
            res.append("SIGKILL signal sent to the jvm.")
            pass
        return {"log": res}

    def kill(self):
        """Forcibly stop the JVM"""
        if not self.isRunning():
            return

        with self._lock:
            self.jvm.kill()

    def join(self):
        if self.thread is None:
            return

        self.thread.join()

    def isRunning(self):
        if self.thread is None:
            return False
        else:
            return self.thread.is_alive()

    def getStatus(self):
        status = MinecraftStatus.UNAVAILABLE
        with self._lock:
            status = copy.copy(self.status)
        return status

    def acquireLock(self):
        """
        Acquire the status change lock non blockingly.
        the lock is aquired if and only if True is returned
        """
        return self._lock.acquire(False)

    def releaseLock(self):
        """
        Release the status change lock.
        Call this method after calling aquireLock()
        """
        if self._lock.locked():
            return self._lock.release()

    def asRcon(self, command):
        """
        Open a RCON connection to the minecraft java server if needed and then send the command.
        Do not forget to call closeRcon when you sent all the commands you wanted to free the resource.
        """
        if self.isRunning() :
            rconCli = rcon.RCONClient("127.0.0.1", self.properties.getProperty("rcon.port"), self.properties.getProperty("rcon.password"))
            res = rconCli.send(command)
            return res
        else:
            raise InternalError("Server not started")

    def backup(self):
        """
        Thread safe backup method
        """
        try:
            if not self.acquireLock():
                return { "code" : 503, "status": self.getStatus().name, "error": "Minecraft server is busy. Try again later."}

            if self.status in [MinecraftStatus.DOWNLOADING, MinecraftStatus.UPLOADING]:
                return { "code" : 503, "status": self.status.name, "error": "A backup operation is aleady running. Try again later."}

            backup = self._backup()
            if self.args.auto_upload :
                self._upload(backup)
            backup["code"] = 200
            backup["status"] = self.status.name
            return backup
        finally:
            self.releaseLock()

    def _populateProperties(self):
        """
        Read the properties file and read the environment to look for the properties to add to server.properties.
        Then write the configuration so the JVM will take it into account on start.
        """
        self.properties.populateProperties()
        self.properties.write()
