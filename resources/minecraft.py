#!/usr/bin/python3

import threading
import subprocess
import logging
import rcon
import argparse
import os.path
import re
import json
import copy
import time
import tarfile
import gzip
import shutil
import sys
import traceback
import distutils.util
import stat
from enum import Enum
from queue import Queue
from mcdownloader import MCDownloader

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
            workPath = os.path.abspath(args.workdir)
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
            if not self.args.use_gfirst:
                command.append(str.format("-XX:ParallelGCThreads={CPU_COUNT}", CPU_COUNT=self.args.gc_threads)) 
            else:
                command.append("-XX:+UseG1GC")
            command.append("-jar")
            command.append(args.jar)
            command.append(args.opt)
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


class MinecraftWrapper(rcon.RCONServerHandler):
    """
    A wrapper for the minecraft java server. This wrapper manage the server and can be used remotely using the RCON protocol.
    (https://developer.valvesoftware.com/wiki/Source_RCON_Protocol)
    If you send a RCON command to this wrapper of form 'minecraft ...' then the command will be interpreted as a command for this wrapper.
    Some examples of commands:
        - minecraft status
        - minecraft start
        - minecraft stop
        - minecraft backup
    any command that does no begin with 'minecraft' will be forwarded to the minecraft server.
    Some example of commands you could want to forward to the server:
        - op myplayername
        - save-all
        - list
        ...
    """

    def __init__(self, args):
        self.args = args
        #self.workerThread = MinecraftWorkerThread(args)
        self.minecraftServer = MinecraftServer(args)
        if not self.args.no_auto_start :
            self.minecraftServer.start()
        else:
            logging.info("NOTICE: Automatic start disabled by configuration. Send the 'minecraft start' command to start the server.")

        if self.args.auto_clean :
            cleanScript="/etc/cron.daily/minecleaning"
            shutil.copyfile("/usr/local/minecraft/cleaning.sh", cleanScript)
            st = os.stat(cleanScript)
            os.chmod(cleanScript, st.st_mode | stat.S_IEXEC)
        if self.args.auto_backup:
            backupScript="/etc/cron.{frequency}/minebackup".format(frequency=self.args.backup_frequency)
            shutil.copyfile("/usr/local/minecraft/backup.sh", backupScript)
            st = os.stat(backupScript)
            os.chmod(backupScript, st.st_mode | stat.S_IEXEC)
        if self.args.auto_clean or self.args.auto_backup:
            self.cron = subprocess.Popen("cron")

        if not os.path.isdir("/root/.ssh"):
            os.mkdir("/root/.ssh")
        if os.listdir("/minecraft/ssh"):
            subprocess.check_call("cp /minecraft/ssh/id_* /root/.ssh", shell=True)
            subprocess.check_call("chmod 600 /root/.ssh/id_*", shell=True)
            subprocess.check_call("chmod 644 /root/.ssh/id_*.pub", shell=True)

    def asRcon(self, command):
        return self.minecraftServer.asRcon(command)

    def mc_start(self):
        """
        Start the minecraft java server thread.
        """
        self.minecraftServer.start()
        time.sleep(0.2)
        return { "code" : 200, "status": self.getStatus().name}

    def mc_stop(self):
        """
        Stop the minecraft java server gracefully if possible.
        """
        try:
            res = self.minecraftServer.stop()
            time.sleep(0.2)
            res["code"] = 200
            res["status"] = self.getStatus().name
            return res
        except InternalError as e :
            return { "code" : 206, "status": self.getStatus().name, "error": e.message}

    def mc_backup(self):
        return self.minecraftServer.backup()

    def fowardCommand(self, command):
        res = self.asRcon(command)
        return { "code" : 200, "log": res}

    def handleRequest(self, command):
        try:
            args = command.split()
            cmd = args[0].lower()
            if cmd == "minecraft":
                action = args[1].lower()
                if action == "start":
                    return json.dumps(self.mc_start())
                elif action == "stop":
                    return json.dumps(self.mc_stop())
                elif action == "status":
                    return json.dumps({ "code" : 200, "status": self.getStatus().name})
                elif action == "backup":
                    return json.dumps(self.mc_backup())
                elif action == "health_status":
                    if self.minecraftServer.isRunning():
                        return json.dumps(self.fowardCommand("list"))
                    else:
                        return json.dumps({ "code" : 200, "status": self.getStatus().name})
                elif action == "property" :
                    key = args[2]
                    if len(args) > 3 :
                        # its a set request
                        if self.minecraftServer.isRunning():
                            return json.dumps({ "code" : 409, "status": self.getStatus().name, "error": "cannot change a property on a running server."})
                        value=" ".join(args[3:])
                        os.environ["MCCONF_{key}".format(key=key)] = value
                        return json.dumps({ "code" : 200, "status": self.getStatus().name})
                    else :
                        # its a get request
                        try:
                            properties = PropertiesFile(os.path.join(self.args.workdir, "server.properties"))
                            properties.populateProperties()
                            return  json.dumps({ "code" : 200, "status": self.getStatus().name, "value" : properties.getProperty(key)})
                        except:
                            return  json.dumps({ "code" : 404, "status": self.getStatus().name, "error" : "key not available"})
                elif action == "config":
                    dictArgs = vars(self.args)
                    if len(args) == 2 :
                        return  json.dumps({ "code" : 200, "status": self.getStatus().name, "config" : dictArgs})
                    else:
                        key = args[2]
                        key = key.replace("-", "_")
                        if not key in dictArgs:
                            return  json.dumps({ "code" : 404, "status": self.getStatus().name, "error" : "bad configuration key"})
                        elif len(args) == 3:
                            return  json.dumps({ "code" : 200, "status": self.getStatus().name, "value" : dictArgs[key]})
                        else:
                            if self.minecraftServer.isRunning():
                                return json.dumps({ "code" : 409, "status": self.getStatus().name, "error": "cannot change a config on a running server."})
                            value=" ".join(args[3:])
                            # lets find the actual type of the config and set the value
                            if isinstance(dictArgs[key], bool):
                                dictArgs[key] = bool(distutils.util.strtobool(value))
                            elif isinstance(dictArgs[key], int):
                                dictArgs[key] = int(value)
                            elif isinstance(dictArgs[key], str):
                                dictArgs[key] = value
                            else:
                                return  json.dumps({ "code" : 404, "status": self.getStatus().name, "error" : "this configuration cannot be changed remotely"})
                            return  json.dumps({ "code" : 200, "status": self.getStatus().name, "value" : dictArgs[key]})
                    print(json.dumps(self.args))
                    return  json.dumps({ "code" : 404, "status": self.getStatus().name, "error" : "key not available"})
                elif action == "set-version":
                    if self.minecraftServer.isRunning():
                        return json.dumps({ "code" : 409, "status": self.getStatus().name, "error": "cannot change the version on a running server."})
                    version = args[2]

                    try:
                        downloader=MCDownloader.getInstance(version)
                        downloader.download()
                        return json.dumps({ "code" : 200, "status": self.getStatus().name})
                    except NameError as e:
                        return json.dumps({ "code" : 500, "status": self.getStatus().name, "error": str(e)})
                    except IOError as e:
                        return json.dumps({ "code" : 500, "status": self.getStatus().name, "error": str(e)})
                else:
                    return json.dumps({"code": 501, "error": "{0} not implemented!".format(action)})
            else:
                return json.dumps(self.fowardCommand(command))
        except InternalError as e :
            logging.exception(e)
            return json.dumps({ "code" : 500, "status": self.getStatus().name, "error": e.message})
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            respStr= str.format("Error: exception cautgh. {}", traceback.format_exception(exc_type, exc_value, exc_traceback)[-1])
            logging.exception(exc_type)
            return json.dumps({ "code" : 500, "status": self.getStatus().name, "error": respStr})

    def serve(self):
        try:
            rconSrv = rcon.RCONServer('', self.args.rcon_port, self.args.rcon_pswd, self)
            rconSrv.run()
        finally:
            if self.minecraftServer.isRunning():
                self.minecraftServer.stop()
            self.minecraftServer.join()

    def getStatus(self):
        return self.minecraftServer.getStatus()

def getBoolEnv(env_var, default=False):
    return bool(distutils.util.strtobool(os.getenv(env_var, str(default))))

FORMAT = '%(asctime)-15s [%(name)s][%(levelname)s]: %(message)s'
logging.basicConfig(format=FORMAT, level="WARNING")

cronFrequencies = ["daily", "hourly", "monthly", "weekly"]

MC_SSH_REMOTE_URL = os.getenv("MC_SSH_REMOTE_URL", "")
MC_MIN_HEAP = os.getenv("MC_MIN_HEAP", os.getenv("MINHEAP", "2048"))
MC_MAX_HEAP = os.getenv("MC_MAX_HEAP", os.getenv("MAXHEAP", "6144"))
MC_BACKUP_FREQUENCY = os.getenv("MC_BACKUP_FREQUENCY", "weekly")

if not MC_BACKUP_FREQUENCY in cronFrequencies:
    logging.FATAL("invalid backup frequency %s. Value must be one of %s", MC_BACKUP_FREQUENCY, cronFrequencies)
    sys.exit(1)

parser = argparse.ArgumentParser(description='Manage a minecraft java server')
parser.add_argument('-v', '--verbose', action="store_true", help="Increase output verbosity")
parser.add_argument('-vv', '--very-verbose', action="store_true", help="Increase output verbosity")
parser.add_argument('-j' , "--jar", default="/minecraft/minecraft_server.jar", help='The jar file for the minecraft server.')
parser.add_argument('-o', "--opt", default="nogui", help='The arguments of the minecraft server. "nogui" by default.')
parser.add_argument('-w', "--workdir", default="/minecraft/server", help='The working directory of the minecraft java server.')
parser.add_argument('-b', "--backup-dir", default="/minecraft/backup", help='The directory where to store the backups localy')
parser.add_argument("--min-heap", default=MC_MIN_HEAP, help='The min heap allocated to the jvm')
parser.add_argument("--max-heap", default=MC_MAX_HEAP, help='The max heap allocated to the jvm')
parser.add_argument("--use-gfirst", action="store_true", help='Use the G1 Garbage Collector instead of the Parallel Garbage Collector')
parser.add_argument("--gc-threads", default="3", help='Number of threads allocated to be Garbage Collector')
parser.add_argument("--rcon-port", default=25575, type=int, help='the listening port for RCON(Remote CONsole)')
parser.add_argument("--rcon-pswd", default="rcon-passwd", help='the password for RCON(Remote CONsole)')
parser.add_argument("--backup-frequency", default=MC_BACKUP_FREQUENCY, choices=cronFrequencies, help='the frequeny of the world backups.')
parser.add_argument("--no-auto-start", action="store_true", help='avoid the the minecraft server to starts automaticaly.')
parser.add_argument("--auto-clean", action="store_true", help="clean the old backups automaticaly. (acts local backup only)")
parser.add_argument("--auto-backup", action="store_true", help='backup the map automaticaly')
parser.add_argument("--auto-download", action="store_true", help='download the lastet backup of the map before starting')
parser.add_argument("--auto-upload", action="store_true", help='upload the backup on a remote server')
parser.add_argument("--ssh-remote-url", default=MC_SSH_REMOTE_URL, help='the url to access the remote ssh server for backup. ex: backup@backup-instance.fr:/path/to/dir')
parser.add_argument('action', choices=("start", "stop", "backup", "status", "health_status", "command", "property", "config", "set-version", "serve"), help='The action to perform')
parser.add_argument('args', nargs='*', help='arguments of the action')

args = parser.parse_args()
if args.verbose :
    logging.getLogger('').setLevel("INFO")
if args.very_verbose:
    logging.getLogger('').setLevel("DEBUG")

if not args.no_auto_start:
    args.no_auto_start=getBoolEnv("MC_NO_AUTO_START")
if not args.auto_clean:
    args.auto_clean=getBoolEnv("MC_AUTO_CLEAN", getBoolEnv("DOCLEANING"))
if not args.auto_backup:
    args.auto_backup=getBoolEnv("MC_AUTO_BACKUP", getBoolEnv("DOBACKUP"))
if not args.auto_download:
    args.auto_download=getBoolEnv("MC_AUTO_DOWNLOAD")
if not args.auto_upload:
    args.auto_upload=getBoolEnv("MC_AUTO_UPLOAD")
if not args.use_gfirst:
    args.use_gfirst=getBoolEnv("MC_USE_GFIRST")

logging.debug(args)
action=args.action
if action in ["start", "stop", "status", "backup", "command", "health_status", "property", "config", "set-version"]:
    try:
        client = rcon.RCONClient("127.0.0.1", args.rcon_port, args.rcon_pswd)
        if action == "command":
            print(client.send(" ".join(args.args)))
        elif action == "health_status":
            resp = client.send("minecraft health_status")
            print(resp)
            resp = json.loads(resp)
            if not resp["code"] == 200:
                sys.exit(1)
        elif action in ["property", "config", "set-version"]:
            print(client.send("minecraft {action} {args}".format(action=action, args=" ".join(args.args))))
        else:
            print(client.send("minecraft {action}".format(action=action)))
    except:
        sys.stderr.write("service unavailable")
        sys.exit(1)
elif action == "serve" :
    wrapper = MinecraftWrapper(args)
    wrapper.serve()
