#!/usr/bin/python2.7

import json
import argparse
import urllib
import sys

# parse command line arguments
parser=argparse.ArgumentParser()
parser.add_argument("-v", "--version", type=str, default="latest", help="the version number of the minecraft server or latest")
parser.add_argument("-t", "--target", type=str, default="release", choices=['release', 'snapshot'], help="precice which lastest version to get from the manifest file when using the latest version")
args=parser.parse_args()

version=""
with open("/tmp/version_manifest.json") as json_data:
  manifest=json.load(json_data)

  if args.version=="latest" :
    print "looking for the latest minecraft "+args.target
    version=manifest[args.version][args.target]
    print "version "+version+" is the latest minecraft "+args.target+"!"

  else :
    print "looking for version "+args.version+" in minecraft available versions"
    for wVersion in manifest["versions"] :
      if wVersion["id"]==args.version :
        version=args.version
	print wVersion["type"]+" "+version+" found!"
        break


print
if not version :
  print "requested version not found!"
  sys.exit(1)

print "Start downloading version: "+version
try:
  jarfile=urllib.URLopener()
  jarfile.retrieve("https://s3.amazonaws.com/Minecraft.Download/versions/"+version+"/minecraft_server."+version+".jar", "/tmp/minecraft_server."+version+".jar")
except IOError as e:
  print "I/O Error. Download aborted "+str(e)
  sys.exit(2)
