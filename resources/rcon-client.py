#!/usr/bin/python2.7

import socket
from struct import *
import binascii
import sys
import argparse

BUFFER_SIZE = 1024

tCOMMAND=2
tLOGIN=3

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
         return pack(format, self.length, self.id, self.type,self.payload,0x0)

    @staticmethod
    def hydrate(bytebuffer):
        paylen=str(len(bytebuffer)-(3*4)-2)
        format='<iii'+paylen+'sh' # see python struct to documentation
        res=RconPacket(0,0,'')
        res.lentgth, res.id, res.type, res.payload, tail = unpack(format, bytebuffer)
        return res



# parse command line arguments
parser=argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", action="store_true", help="increase the informations printed on console")
parser.add_argument("-t", "--target", type=str, default="127.0.0.1:25575", help="target minecraft server. example: 127.0.0.1:25575")
parser.add_argument("-p", "--passwd", type=str, default="rcon-passwd", help="rcon password of the minecraft server")
parser.add_argument('command', metavar='args', type=str, nargs='+', help='command and args destinated to the minecraft server. example: say hello world')
args=parser.parse_args()

if args.verbose :
    print "target:", args.target
    print "passwd:", args.passwd
    print "command:", args.command
#print args.__dict__

# split target to separate address and port
serveradress, serverport= args.target.split(':')

#create the complete command using the received args
command=""
for arg in args.command :
    command+=arg+' '

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect((serveradress, int(serverport)))
except socket.error as e:
    print "Cannot connect to server:", e.strerror
    exit(1)

auth=RconPacket(1, tLOGIN, args.passwd)
MESSAGE=auth.serialize()
#print "authentication", binascii.hexlify(MESSAGE)
s.send(MESSAGE)

data = s.recv(BUFFER_SIZE)
#print "response", binascii.hexlify(data)
answer=RconPacket.hydrate(data)
#print answer.__dict__

# test authentication response
if answer.type != tCOMMAND or answer.id != auth.id :
    sys.stderr.write("authentication failure\n")
    exit(1)

if args.verbose:
    print "authentication success "

packet=RconPacket(2,tCOMMAND,command)
MESSAGE=packet.serialize()
#print "command", binascii.hexlify(MESSAGE)
s.send(MESSAGE)

data = s.recv(BUFFER_SIZE)
#print "response", binascii.hexlify(data)
answer=RconPacket.hydrate(data)
#print answer.__dict__
print answer.payload


s.close()
