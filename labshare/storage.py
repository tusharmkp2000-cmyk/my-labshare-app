"""Storage backends. Same interface, so the app does not care where bytes live.

DiskStore -> local folder (use a Render persistent disk, e.g. /var/data)
S3Store   -> any S3-compatible bucket (AWS S3, Cloudflare R2, Backblaze B2 ...)
"""
import os
import shutil


class DiskStore:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _p(self, key):
        return os.path.join(self.root, *key.split("/"))

    def write(self, key, data):
        path = self._p(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def read(self, key):
        with open(self._p(key), "rb") as f:
            return f.read()

    def list_dirs(self, prefix):
        path = self._p(prefix.rstrip("/"))
        if not os.path.isdir(path):
            return []
        return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))

    def list_keys(self, prefix):
        path = self._p(prefix.rstrip("/"))
        if not os.path.isdir(path):
            return []
        return [(n, os.path.getsize(os.path.join(path, n))) for n in sorted(os.listdir(path))]

    def delete(self, prefix):
        shutil.rmtree(self._p(prefix.rstrip("/")), ignore_errors=True)


class S3Store:
    def __init__(self):
        import boto3
        self.bucket = os.environ["S3_BUCKET"]
        self.c = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT") or None,
            aws_access_key_id=os.environ.get("S3_KEY_ID") or None,
            aws_secret_access_key=os.environ.get("S3_SECRET") or None,
            region_name=os.environ.get("S3_REGION") or None,
        )

    def write(self, key, data):
        self.c.put_object(Bucket=self.bucket, Key=key, Body=data)

    def read(self, key):
        return self.c.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def _pages(self, prefix, **kw):
        pager = self.c.get_paginator("list_objects_v2")
        return pager.paginate(Bucket=self.bucket, Prefix=prefix.rstrip("/") + "/", **kw)

    def list_dirs(self, prefix):
        out = []
        for page in self._pages(prefix, Delimiter="/"):
            out += [p["Prefix"].rstrip("/").rsplit("/", 1)[-1] for p in page.get("CommonPrefixes", [])]
        return sorted(out)

    def list_keys(self, prefix):
        out = []
        for page in self._pages(prefix):
            out += [(o["Key"].rsplit("/", 1)[-1], o["Size"]) for o in page.get("Contents", [])]
        return sorted(out)

    def delete(self, prefix):
        for page in self._pages(prefix):
            for o in page.get("Contents", []):
                self.c.delete_object(Bucket=self.bucket, Key=o["Key"])


def make_store():
    if os.environ.get("S3_BUCKET"):
        return S3Store()
    return DiskStore(os.environ.get("DATA_DIR", "data"))
