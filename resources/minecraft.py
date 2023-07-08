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
from mcs3backup import MinecraftS3BackupManager
import typing
from pathlib import Path

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
    FETCHING = 7

def ignorelogslibs(tarinfo:tarfile.TarInfo) -> (tarfile.TarInfo):
    """
    function to exclude the logs from the backups
    """
    if tarinfo.name.startswith("logs"):
        return None
    elif tarinfo.name.startswith("libraries"):
        return None
    elif tarinfo.name.startswith("versions"):
        return None
    else:
        return tarinfo

class MinecraftServer:

    def __init__(self, args):
        self.thread = None
        self.args = args
        self.properties = PropertiesFile(os.path.join(self.args.workdir, "server.properties"))
        self.status = MinecraftStatus.STOPPED
        self._lock = threading.Lock()
        self.jvm = None
        self.s3_manager = None
        self.logger = logging.getLogger("mc.minecraft")

    def run(self):
        try:
            """Start the JVM"""
            self.logger.info("Server is starting")

            if self.isS3Backuped() and self.args.auto_download:
                with self._lock:
                    self.status = MinecraftStatus.FETCHING
                self.logger.info("fetching remote files")
                self.s3_manager = MinecraftS3BackupManager.buildWith(self.args)
                self.s3_manager.fetchRemote()
            elif self.args.auto_download :
                with self._lock:
                    self.status = MinecraftStatus.DOWNLOADING
                self._download()

            # if auto-download and the workdir is empty
            if self.args.auto_download or not os.listdir(self.args.workdir):
                with self._lock:
                    self.status = MinecraftStatus.LOADING
                if self.isS3Backuped():
                    self.logger.info("pulling remote files")
                    self.s3_manager.pull()
                else:
                    self._load()

            # First lets create the eula.txt file if needed
            workPath = os.path.abspath(self.args.workdir)
            jarPath = Path(self.args.jar).parent
            eulaPath = os.path.join(workPath, "eula.txt")
            if os.path.isfile(eulaPath) == False:
                with open(eulaPath, "w") as eula:
                    eula.write("eula=true\n")

            # Then create or update the server.properties
            self._populateProperties()

            # Check
            if not os.path.exists(self.args.jar):
                raise IOError(f"jar not found {self.args.jar}")

            # Then we can build the java command and run it a subprocess
            command = ["java"]
            command.append(str.format("-Xmx{MAXHEAP}M", MAXHEAP=self.args.max_heap))
            command.append(str.format("-Xms{MINHEAP}M", MINHEAP=self.args.min_heap))
            command.append(f"-javaagent:/{jarPath}/jmx_prometheus_javaagent.jar=9000:/{jarPath}/jmx_prom.yml")
            if not self.args.use_gfirst:
                command.append(str.format("-XX:ParallelGCThreads={CPU_COUNT}", CPU_COUNT=self.args.gc_threads)) 
            else:
                command.append("-XX:+UseG1GC")
            command.append("-jar")
            command.append(self.args.jar)
            command.append(self.args.opt)
            self.logger.info(str(command))
            with self._lock:
                self.jvm = subprocess.Popen(command, cwd=workPath)
            with self._lock:
                self.status = MinecraftStatus.STARTED
            self.jvm.wait()

            if self.args.auto_backup or self.args.auto_upload:
                with self._lock:
                    self.status = MinecraftStatus.SAVING
                self._backup()

        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            respStr= str.format("Error: exception cautgh. {}", traceback.format_exception(exc_type, exc_value, exc_traceback)[-1])
            self.logger.exception(exc_type)

        finally:
            with self._lock:
                self.status = MinecraftStatus.STOPPED
            self.jvm = None
            self.logger.info("Server is stopped")

    def _download(self):
        """
        Download the latest backup from the remote server
        """
        urlParts = self.args.ssh_remote_url.split(":")
        userHost = urlParts[0]
        remotePath = urlParts[1]
        sshCmd = ["ssh", "-o", "StrictHostKeyChecking=no", userHost, "ls -t {0}/*.tar.gz | head -n 1".format(remotePath)]
        self.logger.info("Looking for latest backup: %s", sshCmd)
        res = subprocess.check_output(sshCmd)
        lastbackup = res.decode("utf-8").strip()
        if lastbackup == "":
            self.logger.info("No backup available on remote server.")
            return False

        self.logger.info("latest backup is: %s", lastbackup)
        filepath = os.path.join(self.args.backup_dir, str(lastbackup))
        if os.path.isfile(filepath):
            self.logger.info("latest backup %s is already available locally", lastbackup)
        else:
            scpCmd = ["scp", "-o", "StrictHostKeyChecking=no", "{0}:{1}".format(userHost, os.path.join(remotePath, lastbackup)), self.args.backup_dir]
            self.logger.info("downloading the latest backup")
            res = subprocess.check_output(scpCmd)
            self.logger.debug("Server response: %s", res)

    def _load(self):
        """
        Load the latest local backup to the run directory.
        """
        backups = os.listdir(self.args.backup_dir)
        if not backups:
            self.logger.info("No backup available localy")
            return False

        backups.sort()
        lastbackup = backups[-1]
        self.logger.info("Latest local backup is: %s", lastbackup)
        filepath = os.path.join(self.args.backup_dir, lastbackup)

        self.logger.info("cleaning previous server working dir %s", self.args.workdir)
        for torm in [ os.path.join(self.args.workdir, f) for f in os.listdir(self.args.workdir)]:
            if os.path.isfile(torm):
                os.remove(torm)
            else:
                shutil.rmtree(torm)

        self.logger.info("Extracting backup %s to %s", filepath, self.args.workdir)
        with tarfile.open(name=filepath, mode='r:gz') as tar :
            tar.extractall(path=self.args.workdir)

    def _backup(self) -> typing.Tuple[dict[str, typing.Any], int]:
        if self.isS3Backuped():
            if self.s3_manager is None:
                self.logger.info("no world to backup. server must start at least once.")
                return ({ "log": ["no world to backup"]}, 200)
            self.logger.info("fetching remote and local files for backup")
            if self.args.auto_upload:
                self.s3_manager.fetchRemote()
                self.s3_manager.fetchLocal(filter=ignorelogslibs)

        if not self.isS3Backuped():
            self.logger.info("cleaning old backups")
            backups = os.listdir(self.args.backup_dir)
            if backups is not None and self.args.max_backup_count > 0:
                backups.sort(reverse=True)
                self.logger.debug("%d backup found localy: %s", len(backups), backups)
                if len(backups) >= self.args.max_backup_count:
                    for filename in backups[self.args.max_backup_count-1]:
                        fullpath = os.path.join(self.args.backup_dir,filename)
                        self.logger.info("Removing backup: %s", fullpath)
                        os.remove(fullpath)

        self.logger.info("backuping world")
        res = []
        code = 200
        try:
            # first we save the world and avoid the server from writting the map during the compression
            self.asRcon("say SERVER BACKUP STARTING. Server going readonly...")
            res.append(self.asRcon("save-off"))
            res.append(self.asRcon("save-all"))
        except:
            pass

        if self.isS3Backuped():
            try:
                self.logger.info("pushing world")
                self.s3_manager.push()
            except:
                self.logger.exception("S3 manager failed to push")
                res.append("S3 backup failure")
                code = 503
        else:
            self.properties.read()
            tarName = "{0}_{1}.tar".format(self.properties.getProperty("level-name"), time.strftime("%Y-%m-%d_%Hh%M", time.gmtime()))
            tarFile = os.path.join(self.args.backup_dir, tarName)
            with tarfile.open(name=tarFile, mode='w') as tar :
                tar.add(self.args.workdir, arcname="/", filter=ignorelogslibs)

        try:
            # re-enable the server ability to write the map
            res.append(self.asRcon("save-on"))
            self.asRcon("say SERVER BACKUP ENDED. Server going read-write...")
        except:
            pass

        if not self.isS3Backuped():
            with open(tarFile, 'rb') as f_in:
                with gzip.open('{0}.gz'.format(tarFile), 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            backupFile = "{0}.gz".format(tarName)

            os.remove(tarFile)

            if self.args.auto_upload:
                scpCmd = ["scp", "-o", "StrictHostKeyChecking=no", os.path.join(self.args.backup_dir, backupFile), self.args.ssh_remote_url]
                self.logger.info("uploading world: %s", scpCmd)
                res.append(subprocess.check_output(scpCmd).decode("utf-8"))

            return ({ "log": res, "file" : backupFile }, code)
        else:
            return ({ "log": res}, code)

    def _clean(self) -> typing.Tuple[dict[str, typing.Any], int]:
        code = 200
        try:
            twenty_days_ago = time.time() - (60*60*24*20)
            forty_days_ago = time.time() - (60*60*24*40)
            logs_path = os.path.join(self.args.workdir, "logs")
            res = []
            if os.path.exists(logs_path):
                for f in os.scandir(logs_path):
                    if f.is_file() and f.stat().st_mtime < twenty_days_ago:
                        os.remove(f.path)
                        res.append(f"removed {f.path}")

            for f in os.scandir(self.args.backup_dir):
                if f.is_file() and f.stat().st_mtime < forty_days_ago:
                    os.remove(f.path)
                    res.append(f"removed {f.path}")
        except:
            self.logger.exception("unexpected error", stack_info=True)
            code = 500
        return ({ "log": res}, code)

    def isRemoteBackuped(self) -> bool:
        if self.args.auto_download or self.args.auto_upload:
            return True
        else:
            return False

    def isS3Backuped(self) -> bool:
        if self.args.s3_remote_url and self.isRemoteBackuped():
            return True
        else:
            return False

    def start(self):
        if self.thread and self.thread.is_alive():
            raise InternalError("Server is already running")
        self.thread = threading.Thread(target=self.run, args=(), name="minecraft")
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

            if self.status in [MinecraftStatus.DOWNLOADING, MinecraftStatus.UPLOADING, MinecraftStatus.FETCHING]:
                return { "code" : 503, "status": self.status.name, "error": "A backup operation is aleady running. Try again later."}

            backup, code = self._backup()
            backup["code"] = code
            backup["status"] = self.status.name
            return backup
        finally:
            self.releaseLock()

    def clean(self):
        """
        Thread safe cleaning method
        """
        try:
            if not self.acquireLock():
                return { "code" : 503, "status": self.getStatus().name, "error": "Minecraft server is busy. Try again later."}

            if self.status in [MinecraftStatus.DOWNLOADING, MinecraftStatus.UPLOADING, MinecraftStatus.FETCHING]:
                return { "code" : 503, "status": self.status.name, "error": "A backup operation is running. Try again later."}

            backup, code = self._clean()
            backup["code"] = code
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
