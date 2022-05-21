#!/usr/bin/python3

from email.policy import default
import json
import argparse
import urllib.request
import sys
import shutil
import os.path
import os
import logging
from abc import abstractmethod

# CONSTANTS
VANILLA_MANIFEST_URL="https://launchermeta.mojang.com/mc/game/version_manifest.json"
FABRIC_MANIFEST_URL="https://meta.fabricmc.net/v2/versions"
DOWNLOAD_DIR="/minecraft"

class MCDownloader:

    @abstractmethod
    def _download(self, download_dir=DOWNLOAD_DIR):
        pass

    def download(self, download_dir=DOWNLOAD_DIR):
        jarName=self._download(download_dir)
        link=os.path.join(download_dir, 'minecraft_server.jar')
        if os.path.isfile(link):
            os.unlink(link)
        os.symlink(jarName, link)

    def getInstance(version):
        if version.startswith("fabric-") :
            version=version.partition("fabric-")[2]
            downloader=FabricDownloader(version=version)
        else :
            downloader=VanillaDownloader(version=version)
        return downloader

class VanillaDownloader(MCDownloader):
    """A downloader for Fabric modded Minecraft Server"""
    default_manifest=VANILLA_MANIFEST_URL

    def __init__(self, manifest_url=VANILLA_MANIFEST_URL, version="latest"):
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

    def _download(self, download_dir):
        self.logger.info("Start downloading version metadata : %s", self.versionURL)
        with urllib.request.urlopen(self.versionURL) as response:
            version_manifest=json.loads(response.read().decode('utf-8'))
            
        jarURL=version_manifest["downloads"]["server"]["url"]
        self.logger.info("Start downloading server: %s",jarURL)
        jarName=os.path.join(download_dir, 'minecraft_server.{version}.jar'.format(version=self.versionId))
        jarName=jarName.replace(" ", "_")
        with urllib.request.urlopen(jarURL) as response, open(jarName, 'wb') as jarfile:
            shutil.copyfileobj(response, jarfile)

        return jarName

class FabricDownloader(MCDownloader):
    """A downloader for Fabric modded Minecraft Server"""
    default_manifest=FABRIC_MANIFEST_URL

    def __init__(self, manifest_url=FABRIC_MANIFEST_URL, version="latest"):
        self.logger=logging.getLogger('fabric-downloader')
        self.logger.debug("Fabric Downloader!")

        self.manifest_url=manifest_url

        # fetch the available version for installer, loader and game
        with urllib.request.urlopen("{url}/{document}".format(url=manifest_url, document="installer")) as response:
            installers=json.loads(response.read().decode('utf-8'))
            self.logger.debug("Installers %s", json.dumps(installers))

        with urllib.request.urlopen("{url}/{document}".format(url=manifest_url, document="loader")) as response:
            loaders=json.loads(response.read().decode('utf-8'))
            self.logger.debug("Loaders %s", json.dumps(loaders))

        with urllib.request.urlopen("{url}/{document}".format(url=manifest_url, document="game")) as response:
            games=json.loads(response.read().decode('utf-8'))
            self.logger.debug("Games %s", json.dumps(games))

        if version=="latest" or version=="latest-release" or version=="latest-stable" :
            self.logger.info("looking for the latest minecraft release")
            self.installer=self._getFromManifest(installers, None, True)
            self.loader=self._getFromManifest(loaders, None, True)
            self.versionId=self._getFromManifest(games, None, True)
            self.logger.info("version %s is the latest minecraft release! Fabric-installer=%s, Fabric-loader=%s", self.versionId, self.installer, self.loader)
        elif version=="latest-snapshot" or version=="latest-unstable":
            self.logger.info("looking for the latest minecraft snapshot")
            self.installer=self._getFromManifest(installers, None, True)
            self.loader=self._getFromManifest(loaders, None, True)
            self.versionId=self._getFromManifest(games, None, False)
            self.logger.info("version %s is the latest minecraft snapshot! Fabric-installer=%s, Fabric-loader=%s", self.versionId, self.installer, self.loader)
        else : 
            self.installer=self._getFromManifest(installers, None, True)
            self.loader=self._getFromManifest(loaders, None, True)
            self.versionId=self._getFromManifest(games, version, None)
            self.logger.info("Version=%s, Fabric-installer=%s, Fabric-loader=%s", self.versionId, self.installer, self.loader)

        if self.versionId == None:
            raise NameError('Version "{}" not available!'.format(version))

    def _getFromManifest(self, manifest, version=None, stable=None):
        for entry in manifest:
            if (version == None or entry["version"] == version) and (stable == None or entry["stable"] == stable):
                return entry["version"]

    def _download(self, download_dir):
        # https://meta.fabricmc.net/v2/versions/loader/1.18.1/0.13.3/0.10.2/server/jar /game/loader/installer/server/jar
        jarURL="{url}/loader/{game}/{loader}/{installer}/server/jar".format(url=self.manifest_url, game=self.versionId, loader=self.loader, installer=self.installer)
        self.logger.info("Start downloading server: %s",jarURL)
        jarName=os.path.join(download_dir, 'fabric_server.{version}.jar'.format(version=self.versionId))
        jarName=jarName.replace(" ", "_")
        with urllib.request.urlopen(jarURL) as response, open(jarName, 'wb') as jarfile:
            shutil.copyfileobj(response, jarfile)

        return jarName

# MAIN
def main():
    # parse command line arguments
    parser=argparse.ArgumentParser()
    parser.add_argument("-v", "--version", type=str, default="latest", help="the version number of the minecraft server or latest (latest-release) or even latest-snapshot. Add a 'fabric-' prefix to download fabric instead of a vanilla server.")
    parser.add_argument("-o", "--output-dir", default=DOWNLOAD_DIR, help="output directory for the minecraft_server.jar")
    args=parser.parse_args()

    FORMAT = '%(asctime)-15s [%(name)s][%(levelname)s]: %(message)s'
    logging.basicConfig(format=FORMAT, level="INFO")

    try:
        downloader=MCDownloader.getInstance(args.version)
        downloader.download(args.output_dir)
    except NameError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print("I/O Error. Download aborted. {}".format(e), file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()