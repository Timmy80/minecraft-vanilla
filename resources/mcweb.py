"""
Minecraft web server to control the server
"""

from http.server import CGIHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from jinja2 import Template
import platform
import logging
from minecraft import MinecraftServer, InternalError

class MinecraftWeb(CGIHTTPRequestHandler):
    def __init__(self, minecraft_server: MinecraftServer):
        self.logger = logging.getLogger('mc_web')
        self.minecraft_server = minecraft_server
        self.logger.info("McWeb server started")

    def __call__(self, *args, **kwargs):
        """Handle a request."""
        super().__init__(*args, **kwargs)

    def send_resp(self, ret_val):
        self.server_version = "McWeb/1.0.0"
        self.sys_version = ""
        self.send_response(ret_val)
        self.send_header('Access-Control-Allow-Origin', '*')

    def send_err(self, ret_val, msg):
        self.server_version = "McWeb/1.0.0"
        self.sys_version = ""
        self.send_error(ret_val, msg)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

    def end_get_head(self):
        self.end_headers()
        with open('./mcindex.j2') as f:
            rendered = Template(f.read()).render({
                'mc': {
                    'name': platform.node(),
                    'method': 'GET',
                    'running': self.minecraft_server.isRunning(),
                }
            })
            self.wfile.write(bytes(rendered, "utf-8"))

    def end_post_head(self, result, log):
        self.end_headers()
        with open('./mcindex.j2') as f:
            rendered = Template(f.read()).render({
                'mc': {
                    'name': platform.node(),
                    'method': 'POST',
                    'running': self.minecraft_server.isRunning(),
                    'result': result,
                    'log': log,
                }
            })
            self.wfile.write(bytes(rendered, "utf-8"))

    def do_HEAD(self):
        if self.minecraft_server.isRunning():
            self.send_resp(200)
        else:
            self.send_resp(503)

        self.end_headers()

    def do_GET(self):
        self.send_resp(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.end_get_head()

    def do_POST(self):
        if self.path == "/start":
            try:
                self.minecraft_server.start()
                self.logger.info("Start the minecraft server")
                self.send_resp(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.end_post_head("The Minecraft server is starting", None)
            except InternalError as err:
                self.logger.info("Error during the minecraft server starting: %s" % err)
                self.send_err(500, "Error during the minecraft server starting: %s" % err)
            except:
                self.logger.info("Error during the minecraft server starting")
                self.send_err(500, "Error during the minecraft server starting")
        elif self.path == "/stop":
            try:
                ret = self.minecraft_server.stop()
                self.logger.info("Stop the minecraft server")
                self.send_resp(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                if 'log' in ret:
                    self.end_post_head("The Minecraft server is stopping", ret['log'])
                else:
                    self.end_post_head("The Minecraft server is stopping", None)
            except InternalError as err:
                self.logger.info("Error during the minecraft server stopping: %s" % err)
                self.send_err(500, "Error during the minecraft server stopping: %s" % err)
            except:
                self.logger.info("Error during the minecraft server stopping")
                self.send_err(500, "Error during the minecraft server stopping")
        elif self.path == "/backup":
            try:
                ret = self.minecraft_server.backup()
                self.logger.info("Backup the minecraft server")
                if 'code' in ret:
                    self.send_resp(ret['code'])
                else:
                    self.send_resp(200)

                self.send_header('Content-Type','text/html; charset=utf-8')
                if 'status' in ret:
                    self.end_post_head("Backup of the minecraft server", ret['status'])
                else:
                    self.end_post_head("Backup of the minecraft server", None)
            except InternalError as err:
                self.logger.info("Error during the minecraft server backup: %s" % err)
                self.send_err(500, "Error during the minecraft server backup: %s" % err)
            except:
                self.logger.info("Error during the minecraft server backup")
                self.send_err(500, "Error during the minecraft server backup")
        elif self.path == "/rcon":
            fields = parse_qs(str(self.rfile.read(int(self.headers.get('content-length'))), "UTF-8"))
            if 'rcon' in fields:
                try:
                    rcon_command = fields['rcon'][0]
                    self.logger.info("Send RCON to the minecraft server: %s" % rcon_command)
                    ret = self.minecraft_server.asRcon(rcon_command)

                    self.send_resp(200)
                    self.send_header('Content-Type','text/html; charset=utf-8')
                    self.end_post_head("RCON response", ret)
                except InternalError as err:
                    self.logger.info("Can't execute the RCON command: %s" % err)
                    self.send_err(500, "Can't execute the RCON command: %s" % err)
                except:
                    self.logger.info("Can't execute the RCON command")
                    self.send_err(500, "Can't execute the RCON command")
            else:
                self.send_err(404, "Missing RCON command")
                self.end_headers()
        else:
            self.send_err(404, "The post method %s is invalid" % self.path)
            self.end_headers()

    def run(web_port, minecraft_server: MinecraftServer):
        handler = MinecraftWeb(minecraft_server)
        web_server = HTTPServer(("0.0.0.0", web_port), handler)
        web_server.serve_forever()
