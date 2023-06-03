#!/usr/bin/python3

import threading
import subprocess
import logging
import rcon
import argparse
import os.path
import json
import time
import shutil
import sys
import traceback
import distutils.util
import stat
from mcdownloader import MCDownloader
from minecraft import MinecraftServer, PropertiesFile, InternalError
from mcweb import MinecraftWeb

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
    any command that does not begin with 'minecraft' will be forwarded to the minecraft server.
    Some example of commands you could want to forward to the server:
        - op myplayername
        - save-all
        - list
        ...
    """

    def __init__(self, args) -> None:
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

    def mc_web_start(self):
        self.web_thread = threading.Thread(target=MinecraftWeb.run, args=(self.args.web_port, self.args.web_path_prefix, self.minecraftServer))
        self.web_thread.start()
        return { "code" : 200 }

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
                            if key in ["version", "action", "verbose", "very_verbose", "rcon_port", "rcon_pswd", "jar", "workdir", "backup_dir", "web_port", "backup_frequency", "auto_clean", "no_auto_start"]:
                                return  json.dumps({ "code" : 404, "status": self.getStatus().name, "error" : "this configuration cannot be changed remotely"})
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
        if self.args.web_port > 0:
            self.mc_web_start()

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

def main() -> None:
    FORMAT = '%(asctime)-15s [%(name)s][%(levelname)s]: %(message)s'
    logging.basicConfig(format=FORMAT, level="WARNING")

    cronFrequencies = ["daily", "hourly", "monthly", "weekly"]

    MC_SSH_REMOTE_URL = os.getenv("MC_SSH_REMOTE_URL", "")
    MC_MIN_HEAP = os.getenv("MC_MIN_HEAP", os.getenv("MINHEAP", "2048"))
    MC_MAX_HEAP = os.getenv("MC_MAX_HEAP", os.getenv("MAXHEAP", "6144"))
    MC_WEB_PATH_PREFIX = os.getenv("MC_WEB_PATH_PREFIX", "")
    MC_BACKUP_FREQUENCY = os.getenv("MC_BACKUP_FREQUENCY", "weekly")
    MINECRAFT_VERSION = os.getenv("MINECRAFT_VERSION", "latest-release")

    if not MC_BACKUP_FREQUENCY in cronFrequencies:
        logging.fatal("invalid backup frequency %s. Value must be one of %s", MC_BACKUP_FREQUENCY, cronFrequencies)
        sys.exit(1)

    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('-v', '--verbose', action="store_true", help="Increase output verbosity")
    parent_parser.add_argument('-vv', '--very-verbose', action="store_true", help="Increase output verbosity")
    parent_parser.add_argument("--rcon-port", default=25575, type=int, help='the listening port for RCON(Remote CONsole)')
    parent_parser.add_argument("--rcon-pswd", default="rcon-passwd", help='the password for RCON(Remote CONsole)')

    args_parser = argparse.ArgumentParser(add_help=False)
    args_parser.add_argument('args', nargs='*', help='arguments')

    parser = argparse.ArgumentParser(description='Manage a minecraft java server')#, parents=[parent_parser])

    subparsers = parser.add_subparsers(help='The action to perform', required=True, dest="action")

    serve_parser = subparsers.add_parser("serve", help="Start the internal rcon/web server that manages a minecraft java server.", parents=[parent_parser])
    serve_parser.add_argument('-j' , "--jar", default="/minecraft/minecraft_server.jar", help='The jar file for the minecraft server.')
    serve_parser.add_argument('-o', "--opt", default="nogui", help='The arguments of the minecraft server. "nogui" by default.')
    serve_parser.add_argument('-w', "--workdir", default="/minecraft/server", help='The working directory of the minecraft java server.')
    serve_parser.add_argument('-b', "--backup-dir", default="/minecraft/backup", help='The directory where to store the backups localy')
    serve_parser.add_argument("--min-heap", default=MC_MIN_HEAP, help='The min heap allocated to the jvm')
    serve_parser.add_argument("--max-heap", default=MC_MAX_HEAP, help='The max heap allocated to the jvm')
    serve_parser.add_argument("--use-gfirst", action="store_true", help='Use the G1 Garbage Collector instead of the Parallel Garbage Collector')
    serve_parser.add_argument("--gc-threads", default="3", help='Number of threads allocated to be Garbage Collector')
    serve_parser.add_argument('--web-port', default=0, type=int, help="The listening port of McWeb to control the minecraft server (0 to disable)")
    serve_parser.add_argument('--web-path-prefix', default=MC_WEB_PATH_PREFIX, help="Url path prefix in case of a reverse proxy")
    serve_parser.add_argument("--backup-frequency", default=MC_BACKUP_FREQUENCY, choices=cronFrequencies, help='the frequeny of the world backups.')
    serve_parser.add_argument("--no-auto-start", action="store_true", help='avoid the the minecraft server to starts automaticaly.')
    serve_parser.add_argument("--auto-clean", action="store_true", help="clean the old backups automaticaly. (acts local backup only)")
    serve_parser.add_argument("--auto-backup", action="store_true", help='backup the map automaticaly')
    serve_parser.add_argument("--auto-download", action="store_true", help='download the lastet backup of the map before starting')
    serve_parser.add_argument("--auto-upload", action="store_true", help='upload the backup on a remote server')
    serve_parser.add_argument("--ssh-remote-url", default=MC_SSH_REMOTE_URL, help='the url to access the remote ssh server for backup. ex: backup@backup-instance.fr:/path/to/dir')
    serve_parser.add_argument("--version", default=MINECRAFT_VERSION, help='The vesion of minecraft to install in the image. If it starts with "fabric-" a fabric modded server will be downloaded.')

    subparsers.add_parser("start", help="Start the minecraft java server", parents=[parent_parser])
    subparsers.add_parser("stop", help="Stop the minecraft java server", parents=[parent_parser])
    subparsers.add_parser("backup", help="Backup the minecraft world", parents=[parent_parser])
    subparsers.add_parser("status", help="Get the status of the minecraft server", parents=[parent_parser])
    subparsers.add_parser("health_status", help="Perform a health check", parents=[parent_parser])

    subparsers.add_parser("command", help="Send a rcon command to the minecraft server", parents=[parent_parser, args_parser])
    subparsers.add_parser("property", help="Get or set a property", parents=[parent_parser, args_parser])
    subparsers.add_parser("config", help="Get or set a configuration", parents=[parent_parser, args_parser])

    version_parser = subparsers.add_parser("set-version", help="Set the minecraft version", parents=[parent_parser])
    version_parser.add_argument("version", help='The vesion of minecraft to install in the image. If it starts with "fabric-" a fabric modded server will be downloaded.')


    args = parser.parse_args()
    if args.verbose :
        logging.getLogger('').setLevel("INFO")
    if args.very_verbose:
        logging.getLogger('').setLevel("DEBUG")

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
                json_resp = json.loads(resp)
                if not json_resp["code"] == 200:
                    sys.exit(1)
            elif action == "set-version":
                print(client.send("minecraft {action} {version}".format(action=action, version=args.version)))
            elif action in ["property", "config"]:
                print(client.send("minecraft {action} {args}".format(action=action, args=" ".join(args.args))))
            else:
                print(client.send("minecraft {action}".format(action=action)))
        except:
            sys.stderr.write("service unavailable")
            sys.exit(1)

    elif action == "serve" :
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

        try:
            if not MCDownloader.isDownloaded():
                downloader=MCDownloader.getInstance(args.version)
                downloader.download()
        except NameError as e:
            logging.fatal(e)
            sys.exit(128)
        except IOError as e:
            logging.fatal(e)
            sys.exit(128)
        wrapper = MinecraftWrapper(args)
        wrapper.serve()

if __name__ == "__main__":
    main()
