#!/usr/bin/python3

import json
import argparse
import urllib.request
import sys
import shutil
import os.path
import os

# parse command line arguments
parser=argparse.ArgumentParser()
parser.add_argument("-m", "--manifest", default="https://launchermeta.mojang.com/mc/game/version_manifest.json", help="The launcher manifest to get all the available versions")
parser.add_argument("-v", "--version", type=str, default="latest", help="the version number of the minecraft server or latest (latest-release) or latest-snapshot")
parser.add_argument("-o", "--output-dir", default="/minecraft", help="output directory for the minecraft server jar")
args=parser.parse_args()

version=""
versionURL=""
with urllib.request.urlopen(args.manifest) as response:
  manifest=json.loads(response.read().decode('utf-8'))

  if args.version=="latest" or args.version=="latest-release" :
    print("looking for the latest minecraft release")
    versionId=manifest["latest"]["release"]
    print("version {0} is the latest minecraft release!".format(versionId))
  elif args.version=="latest-snapshot":
    print("looking for the latest minecraft snapshot")
    versionId=manifest["latest"]["snapshot"]
    print("version {0} is the latest minecraft snapshot!".format(versionId))
  else : 
    versionId=args.version

print("looking for version {version} in minecraft available versions".format(version=versionId))
for wVersion in manifest["versions"] :
  if wVersion["id"]==versionId :
    version=versionId
    versionURL=wVersion["url"]
    print("{type} {version} found!".format(type=wVersion["type"], version=version))
    break

print()
if not version :
  print("requested version not found!", file=sys.stderr)
  sys.exit(1)

print("Start downloading version metadata : {0}".format(versionURL))
try:
  with urllib.request.urlopen(versionURL) as response:
    version_manifest=json.loads(response.read().decode('utf-8'))
except IOError as e:
  print("I/O Error. Download aborted "+str(e), file=sys.stderr)
  sys.exit(2)

jarURL=version_manifest["downloads"]["server"]["url"]

print("Start downloading server: {0}".format(jarURL))
try:
  jarName=os.path.join(args.output_dir, 'minecraft_server.{version}.jar'.format(version=version))
  jarName=jarName.replace(" ", "_")
  with urllib.request.urlopen(jarURL) as response, open(jarName, 'wb') as jarfile:
    shutil.copyfileobj(response, jarfile)
except IOError as e:
  print("I/O Error. Download aborted "+str(e), file=sys.stderr)
  sys.exit(2)

link=os.path.join(args.output_dir, 'minecraft_server.jar')
if os.path.isfile(link):
  os.unlink(link)
os.symlink(jarName, link)
