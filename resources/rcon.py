"""
RCON (Remote Console)
Client and server
"""

import logging
import socket
import struct
import binascii
import sys
import traceback

tRESPONSE=0
tCOMMAND=2
tLOGIN=3

class RCONError(Exception):
    """For RCON error management"""

    def __init__(self, *args):
        if args :
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return 'Error: {0}'.format(self.message)
        else:
            return 'RCON error'

class RconPacket:
    """ Definition for MC RCON packet:
    - packet lenth (int)
    - packet id (int)
    - packet type (int) 3 for login, 2 to run a command, 0 for a multi-packet response
    - Payload (byte[]) ASCII text
    - Pad (2 null bytes)"""

    def __init__(self,id,type,payload): #constructor
        self.length=len(payload)+(2*4)+2 #header excluded
        self.id=id
        self.type=type
        self.payload=payload

    def serialize(self):
         paylen=str(len(self.payload))
         format='<iii'+paylen+'sh' # see python struct to documentation
         return struct.pack(format, self.length, self.id, self.type,self.payload.encode("UTF-8"),0x0)

    @staticmethod
    def hydrate(bytebuffer):
        paylen=str(len(bytebuffer)-(3*4)-2)
        format='<iii'+paylen+'sh' # see python struct to documentation
        res=RconPacket(0,0,'')
        res.lentgth, res.id, res.type, res.payload, tail = struct.unpack(format, bytebuffer)
        res.payload = res.payload.decode("UTF-8")
        return res

class RCONServerHandler:

    def handleRequest(self, command):
        return "Error: not implemented"

class RCONServer:
    """A very simple blocking RCON server"""
    BUFFER_SIZE = 1024

    def __init__(self, bindAddr, bindPort, passwd, handler):
        self.bindPort = bindPort
        self.s = socket.socket()
        self.s.bind((bindAddr, bindPort))
        self.s.listen(1)
        self.password = passwd
        self.handler = handler

    def run(self):
        while True: 
            self.logger = logging.getLogger(str.format("rcon.RCON-SRV/{}", self.bindPort))
            try:
                # Establish connection with client. 
                c, addr = self.s.accept()
                self.logger.info("Got connection from %s", addr )
                self.processConnection(c, addr)
                
            except struct.error as e:
                self.logger.error("error: %s", e)
                c.close()
            except KeyboardInterrupt :
                self.s.close()
                return
            except OSError:
                self.s.close()
                return
            except :
                c.close()
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.exception(exc_type)

    def processConnection(self, c, addr):
        self.logger = logging.getLogger(str.format("rcon.RCON-SRV/{}/{}", self.bindPort, addr))
        # Get authentication packet
        auth=self.receive(c)

        # check packet type and password
        if auth.type != tLOGIN or auth.payload != self.password:
            # reply authentication error
            self.logger.info("Authentication failure")
            self.reply(c, RconPacket(-1, tCOMMAND,""))
            c.close()
            return

        # reply authentication OK
        self.logger.info("Authentication success")
        self.reply(c, RconPacket(auth.id, tCOMMAND, ""))

        # Get command packet
        command=self.receive(c)

        # check packet type
        if command.type != tCOMMAND :
            # reply authentication error
            error = str.format("Error: Command packet expected. But type {type} received", type=command.type)
            self.logger.error(error)
            self.reply(c, RconPacket(command.id, tRESPONSE, error))
            c.close()
            return
        
        # process the command
        self.logger.info("command received. id=%d cmd=%s", command.id, command.payload)
        try:
            respStr = self.handler.handleRequest(command.payload)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            respStr= str.format("Error: exception cautgh. {}", traceback.format_exception(exc_type, exc_value, exc_traceback)[-1])
            logging.exception(exc_type)

        # build & send the response
        if respStr is None:
            respStr = ""
        self.reply(c, RconPacket(command.id, tRESPONSE, respStr))
        c.close()

    def receive(self, c):
        data = c.recv(RCONServer.BUFFER_SIZE)
        self.logger.debug("receive:%s", binascii.hexlify(data))
        return RconPacket.hydrate(data)

    def reply(self, c, resp):
        MESSAGE=resp.serialize()
        self.logger.debug("send:%s", binascii.hexlify(MESSAGE))
        c.send(MESSAGE)

    def close(self):
        self.s.close()

class RCONClient:
    """A very simple RCON client"""
    BUFFER_SIZE = 1024

    def __init__(self, serveradress, serverport, passwd):
        self.logger = logging.getLogger(str.format("rcon.RCON-CLI/{}", serverport))
        self.id = 0
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.s.connect((serveradress, int(serverport)))
        except socket.error as e:
            self.logger.error("Cannot connect to server: %s", e.strerror)
            raise e

        auth=RconPacket(self.allocateId(), tLOGIN, passwd)
        MESSAGE=auth.serialize()
        self.logger.debug("authentication %s", binascii.hexlify(MESSAGE))
        self.s.send(MESSAGE)

        answer=self.receive(self.s)

        # test authentication response
        if answer.type != tCOMMAND or answer.id != auth.id :
            raise RCONError("authentication failure")

        self.logger.info("authentication success ")

    def allocateId(self):
        self.id = self.id + 1
        return self.id

    def send(self, command) -> str:
        packet=RconPacket(self.allocateId(),tCOMMAND,command)
        MESSAGE=packet.serialize()
        self.logger.debug("command %s", binascii.hexlify(MESSAGE))
        self.s.send(MESSAGE)

        answer=self.receive(self.s)
        return answer.payload

    def receive(self, c):
        data = c.recv(RCONClient.BUFFER_SIZE)
        return RconPacket.hydrate(data)

    def close(self):
        self.s.close()