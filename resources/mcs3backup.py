#!/usr/bin/python3

from __future__ import annotations
import logging
from pathlib import Path
import typing
import boto3
from botocore.client import Config
import json
import hashlib
import os
import tarfile

def filterNothing(tarinfo:tarfile.TarInfo) -> (tarfile.TarInfo | None):
    """
    function to accept anyfile
    """
    return tarinfo

class StoredObject:

    def __init__(self, object) -> None:
        self.object = object

    def objectName(self) -> str:
        return self.object['Key']
    
    def fileDigest(self) -> str:
        md5_digest = self.object['ETag']
        md5_digest = md5_digest.replace('"', '')
        return md5_digest
    
class LocalFile:

    def __init__(self, fileName: str, path: Path) -> None:
        self.fileName = fileName
        self.path = path
        self.md5Digest = LocalFile.md5(path)
    
    def fileDigest(self) -> str:
        return self.md5Digest

    @staticmethod
    def md5(fname: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(fname, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

class MinecraftS3BackupManager:

    def __init__(self, localDirectory: Path, bucketName: str, client) -> None:
        self.logger = logging.getLogger("mc.MinecraftS3BackupManager")
        self.localDirectory = localDirectory
        self.bucketName = bucketName
        self.client = client
        self.remoteObjects=dict[str, StoredObject]()
        self.localFiles=dict[str, LocalFile]()

        assert self.localDirectory.is_dir()
        pass

    def fetchRemote(self) -> None:
        """
        Fetch the informations about the bucket and its objects
        """
        objects = self.client.list_objects_v2(Bucket=self.bucketName)

        remote_objects=dict[str, StoredObject]()
        if "Contents" in  objects:
            for obj in objects['Contents']:
                so = StoredObject(obj)
                remote_objects[so.objectName()] = so
                self.logger.debug("fetched remote object %s digest %s", so.objectName(), so.fileDigest())
        else:
            self.logger.debug("fetched bucket is empty")

        self.remoteObjects = remote_objects

    def fetchLocal(self, filter:typing.Callable[[tarfile.TarInfo], tarfile.TarInfo | None]=filterNothing):
        """
        Fetch the informations about the files under the localDirectory
        """
        self.localFiles = self._listDir(self.localDirectory, self.localDirectory, filter)

    def _listDir(self, parentPath: Path, path: Path, filter:typing.Callable[[tarfile.TarInfo], tarfile.TarInfo | None]) -> dict[str, LocalFile]:
        """
        Recusively fetch a directory and relativize the paths
        """
        local_files=dict[str, LocalFile]()
        for f in os.scandir(path):
            if f.is_dir():
                local_files.update(self._listDir(parentPath, Path(f.path), filter))
            else:
                path = Path(f.path)
                relpath = path.relative_to(parentPath)
                key=str(relpath)
                if filter(tarfile.TarInfo(name=key)) is None:
                    continue

                lf=LocalFile(key, path)
                local_files[key]=lf
                self.logger.debug("fetched local file %s digest %s", key, lf.fileDigest())

        return local_files
    
    def pull(self) -> None:
        """
        Pull the files from the bucket to the localDirectory
        """
        for object in self.remoteObjects.values():
            o = Path(os.path.join(self.localDirectory, object.objectName()))
            o.parent.mkdir(parents=True, exist_ok=True)

            with o.open('wb') as f:
                self.client.download_fileobj(self.bucketName, object.objectName(), f)

    def changedFiles(self) -> dict[str, LocalFile]:
        """
        Find the files that differs from the s3 bucket according to their checksum

        A call to fetchRemote() and fetchLocal() MUST be done prior to use this method
        """
        changed = self.localFiles.copy() # at first we consider all file changed
        for k,v in self.localFiles.items():
            hash = v.fileDigest()
            if k in self.remoteObjects:
                object = self.remoteObjects[k]
                self.logger.debug("Compare %s local %s remote %s", k, v.fileDigest(), object.fileDigest())
                if hash == object.fileDigest():
                    changed.pop(k)
                else:
                    self.logger.info("file %s modified localy", k)
            else:
                    self.logger.info("file %s created localy", k)

        return changed
    

    def removedFiles(self) -> dict[str, StoredObject]:
        """
        Find the files that exist only on the s3 bucket according to their presence in the local directory

        A call to fetchRemote() and fetchLocal() MUST be done prior to use this method
        """
        removed = self.remoteObjects.copy() # at first we consider all file changed
        for k,v in self.remoteObjects.items():
            if k in self.localFiles:
                removed.pop(k)
            else:
                self.logger.info("file %s removed localy", k)

        return removed
    
    def push(self) -> None:
        """
        Push the changes to the bucket. Upload changed files and delete the removed files.
        """
        to_upload = self.changedFiles()
        to_remove = self.removedFiles()

        for k,v in to_upload.items():
            self.logger.info("uploading %s", k)
            with v.path.open("rb") as f:
                self.client.upload_fileobj(f, self.bucketName, k)

        for k in to_remove.keys():
            self.logger.info("removing %s", k)
            self.client.delete_object(Key=k, Bucket=self.bucketName)


    @staticmethod
    def buildWith(args) -> MinecraftS3BackupManager:
        """
        Use arguments from argpars to build a new s3 client and initialize an instance of MinecraftS3BackupManager
        """
        secret = None
        with open(args.s3_key_secret, "r") as f:
            secret = f.readline().strip()

        s3_client = boto3.client('s3', 
            endpoint_url=args.s3_remote_url,
            aws_access_key_id=args.s3_key_id,
            aws_secret_access_key=secret,
            region_name=args.s3_region
            )
        mn =  MinecraftS3BackupManager(Path(args.workdir), args.s3_bucket, s3_client)
        return mn


def main():
    import argparse

    MC_S3_REMOTE_URL = os.getenv("MC_S3_REMOTE_URL", "")
    MC_S3_BUCKET = os.getenv("MC_S3_BUCKET", "")
    MC_S3_REGION = os.getenv("MC_S3_REGION", "")
    MC_S3_KEY_ID = os.getenv("MC_S3_KEY_ID", "")
    MC_S3_KEY_SECRET = os.getenv("MC_S3_KEY_SECRET", "")

    parser = argparse.ArgumentParser(description='Manage a minecraft S3 backup')
    parser.add_argument('-w', "--workdir", default="/minecraft/server", help='The working directory of the minecraft java server.')
    parser.add_argument("--s3-remote-url", default=MC_S3_REMOTE_URL, help='the url to access the remote object storage server for backup. ex: https://s3.gra1.standard.cloud.ovh.net')
    parser.add_argument("--s3-bucket", default=MC_S3_BUCKET, help='the bucket of the remote object storage server for backup. ex: minecraft-world')
    parser.add_argument("--s3-region", default=MC_S3_REGION, help='the region of the remote object storage server for backup. ex: gra1')
    parser.add_argument("--s3-key-id", default=MC_S3_KEY_ID, help='the key id of the remote object storage server for backup.')
    parser.add_argument("--s3-key-secret", default=MC_S3_KEY_SECRET, help='path to the secret for the object storage secret key. ex: /run/secrets/s3_key')
    args = parser.parse_args()


    FORMAT = '%(asctime)-15s [%(name)s][%(levelname)s]: %(message)s'
    logging.basicConfig(format=FORMAT, level="DEBUG")

    logging.getLogger("botocore").setLevel("INFO")
    
    mn =  MinecraftS3BackupManager.buildWith(args)
    mn.fetchRemote()
    mn.fetchLocal()
    mn.push()

    #for f,v in mn.localFiles.items():
    #    print(f, " ", v.path, " ", v.md5Digest)

if __name__ == "__main__":
    main()