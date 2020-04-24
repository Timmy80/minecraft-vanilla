#!/usr/bin/python3

import json
import argparse
import urllib.request
import sys
import shutil
import os.path

# parse command line arguments
parser=argparse.ArgumentParser()
parser.add_argument("-m", "--manifest", default="https://launchermeta.mojang.com/mc/game/version_manifest.json", help="The launcher manifest to get all the available versions")
parser.add_argument("-v", "--version", type=str, default="latest", help="the version number of the minecraft server or latest")
parser.add_argument("-t", "--target", type=str, default="release", choices=['release', 'snapshot'], help="precice which lastest version to get from the manifest file when using the latest version")
parser.add_argument("-o", "--output-dir", default="/minecraft", help="output directory for the minecraft server jar")
args=parser.parse_args()

version=""
versionURL=""
with urllib.request.urlopen(args.manifest) as response:
  manifest=json.loads(response.read().decode('utf-8'))

  if args.version=="latest" :
    print("looking for the latest minecraft "+args.target)
    tmpVersion=manifest[args.version][args.target]
    print("version "+tmpVersion+" is the latest minecraft "+args.target+"!")
    for wVersion in manifest["versions"] : 
      if wVersion["id"]==tmpVersion :
        version=tmpVersion
        versionURL=wVersion["url"]
        print(wVersion["type"]+" "+version+" found!")
        break

  else : 
    print("looking for version {version} in minecraft available versions".format(version=args.version))
    for wVersion in manifest["versions"] :
      if wVersion["id"]==args.version :
        version=args.version
        versionURL=wVersion["url"]
        print(wVersion["type"]+" "+version+" found!")
        break

print
if not version :
  print("requested version not found!")
  sys.exit(1)

print("Start downloading version metadata : "+versionURL)
try:
  with urllib.request.urlopen(versionURL) as response:
    version_manifest=json.loads(response.read().decode('utf-8'))
except IOError as e:
  print("I/O Error. Download aborted "+str(e))
  sys.exit(2)

jarURL=version_manifest["downloads"]["server"]["url"]

print("Start downloading server: "+jarURL)
try:
  jarName=os.path.join(args.output_dir, 'minecraft_server.{version}.jar'.format(version=version))
  jarName=jarName.replace(" ", "_")
  with urllib.request.urlopen(jarURL) as response, open(jarName, 'wb') as jarfile:
    shutil.copyfileobj(response, jarfile)
except IOError as e:
  print("I/O Error. Download aborted "+str(e))
  sys.exit(2)
