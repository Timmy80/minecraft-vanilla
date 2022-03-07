#!/usr/bin/python3

import json
import argparse
import urllib.request
import sys
import shutil
import os.path
import os
import logging

# CONSTANTS
MANIFEST_URL="https://launchermeta.mojang.com/mc/game/version_manifest.json"
DOWNLOAD_DIR="/minecraft"

class VanillaDownloader:
    """A downloader for Fabric modded Minecraft Server"""

    def __init__(self, manifest_url=MANIFEST_URL, version="latest"):
        self.logger=logging.getLogger('vanilla-downloader')
        self.logger.debug("Vanilla Downloader!")

        self.manifest_url=manifest_url

        # fetch the available version for installer, loader and game
        with urllib.request.urlopen(manifest_url) as response:
            manifest=json.loads(response.read().decode('utf-8'))

        if version=="latest" or version=="latest-release" :
            self.logger.info("looking for the latest minecraft release")
            self.versionId=manifest["latest"]["release"]
            self.logger.info("version %s is the latest minecraft release!", self.versionId)
        elif version=="latest-snapshot":
            self.logger.info("looking for the latest minecraft snapshot")
            self.versionId=versionId=manifest["latest"]["snapshot"]
            self.logger.info("version %s is the latest minecraft snapshot!", self.versionId)
        else : 
            self.versionId=version

        self.logger.info("looking for version %s in minecraft available versions",self.versionId)
        for wVersion in manifest["versions"] :
            if wVersion["id"]==self.versionId :
                self.version=self.versionId
                self.versionURL=wVersion["url"]
                self.logger.info("%s %s found!",wVersion["type"], self.version)
                break

        if not self.version :
            raise NameError("requested version '{}' not found!".format(version))

    def download(self, download_dir=DOWNLOAD_DIR):
        self.logger.info("Start downloading version metadata : %s", self.versionURL)
        with urllib.request.urlopen(self.versionURL) as response:
            version_manifest=json.loads(response.read().decode('utf-8'))
            
        jarURL=version_manifest["downloads"]["server"]["url"]
        self.logger.info("Start downloading server: %s",jarURL)
        jarName=os.path.join(download_dir, 'minecraft_server.{version}.jar'.format(version=self.versionId))
        jarName=jarName.replace(" ", "_")
        with urllib.request.urlopen(jarURL) as response, open(jarName, 'wb') as jarfile:
            shutil.copyfileobj(response, jarfile)

        link=os.path.join(download_dir, 'minecraft_server.jar')
        if os.path.isfile(link):
            os.unlink(link)
        os.symlink(jarName, link)

# MAIN
def main():
    # parse command line arguments
    parser=argparse.ArgumentParser()
    parser.add_argument("-m", "--manifest", default=MANIFEST_URL, help="The launcher manifest to get all the available versions")
    parser.add_argument("-v", "--version", type=str, default="latest", help="the version number of the minecraft server or latest (latest-release) or latest-snapshot")
    parser.add_argument("-o", "--output-dir", default="/minecraft", help="output directory for the minecraft server jar")
    args=parser.parse_args()

    FORMAT = '%(asctime)-15s [%(name)s][%(levelname)s]: %(message)s'
    logging.basicConfig(format=FORMAT, level="INFO")

    try:
        downloader=VanillaDownloader(args.manifest, args.version)
        downloader.download(args.output_dir)
    except NameError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print("I/O Error. Download aborted. {}".format(e), file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()