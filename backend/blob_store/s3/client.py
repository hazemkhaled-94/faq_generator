"""Connection to the S3 object store.

The only module that knows boto3 exists or where the store lives.

Any S3 implementation, named by its endpoint: SeaweedFS and MinIO on a
path-style endpoint of their own, AWS S3 on none, R2 and B2 and Spaces on
theirs. What differs between them is an address, a region and an addressing
style, so those are the three settings; every operation the buckets use is
core S3 and spelled the same everywhere.

An empty value means **let boto3 decide**, and that is what makes AWS
reachable: it resolves its own endpoint from the region and finds its own
credentials from the instance role. The names must still be SET, empty or
not - a deployment that forgot the file gets a KeyError here rather than a
quiet fallback to somebody's real AWS account.
"""

from __future__ import annotations

import os
from functools import lru_cache

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from blob_store.store import Entry


@lru_cache(maxsize=1)
def s3_client():
    """Builds the S3 client, once per process.

    Raises:
        KeyError: If any of the five names is unset. Empty is a value and
            means the SDK's own default; absent is a missing configuration.
    """
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"] or None,
        aws_access_key_id=os.environ["S3_ACCESS_KEY"] or None,
        aws_secret_access_key=os.environ["S3_SECRET_KEY"] or None,
        region_name=os.environ["S3_REGION"] or None,
        config=BotoConfig(
            signature_version="s3v4",
            # Path style is what a self-hosted gateway expects, because the
            # virtual-host style boto3 prefers resolves buckets as
            # subdomains. AWS wants `auto`, and says so in .env.example.
            s3={"addressing_style": os.environ["S3_ADDRESSING_STYLE"] or None},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
        ),
    )


#: The error codes that mean "no such object", across the spellings S3
#: implementations use for a head request.
_ABSENT = frozenset({"404", "NoSuchKey", "NotFound"})

#: How many keys one delete request carries. The S3 limit.
_BATCH = 1000


def _absent(exc: ClientError) -> bool:
    """Whether a client error means there was no such object."""
    return exc.response.get("Error", {}).get("Code") in _ABSENT


class S3Store:
    """The `ObjectStore` over any S3 implementation, with the client it is given."""

    def __init__(self, client) -> None:
        self._client = client

    def put(self, bucket, key, data, *, content_type, metadata=None) -> None:
        """See `ObjectStore.put`."""
        self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata=dict(metadata or {}),
        )

    def get(self, bucket, key):
        """See `ObjectStore.get`."""
        try:
            return self._client.get_object(Bucket=bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if _absent(exc):
                return None
            raise

    def exists(self, bucket, key) -> bool:
        """See `ObjectStore.exists`."""
        try:
            self._client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if _absent(exc):
                return False
            raise
        return True

    def delete(self, bucket, key) -> None:
        """See `ObjectStore.delete`."""
        self._client.delete_object(Bucket=bucket, Key=key)

    def copy(self, bucket, key, to_bucket, to_key) -> bool:
        """See `ObjectStore.copy`."""
        try:
            self._client.copy_object(
                Bucket=to_bucket,
                Key=to_key,
                CopySource={"Bucket": bucket, "Key": key},
            )
        except ClientError as exc:
            if _absent(exc):
                return False
            raise
        return True

    def listed(self, bucket, prefix=""):
        """See `ObjectStore.listed`."""
        return [
            Entry(entry["Key"], entry["Size"], entry["LastModified"])
            for page in self._client.get_paginator("list_objects_v2").paginate(
                Bucket=bucket, Prefix=prefix
            )
            for entry in page.get("Contents", [])
        ]

    def delete_many(self, bucket, keys) -> None:
        """See `ObjectStore.delete_many`."""
        for start in range(0, len(keys), _BATCH):
            answer = self._client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [{"Key": key} for key in keys[start : start + _BATCH]]
                },
            )
            if errors := answer.get("Errors"):
                raise RuntimeError(
                    f"the store refused to delete {len(errors)} object(s), "
                    f"first {errors[0].get('Key')}: {errors[0].get('Code')}"
                )

    def has_bucket(self, bucket) -> bool:
        """See `ObjectStore.has_bucket`."""
        try:
            self._client.head_bucket(Bucket=bucket)
        except ClientError as exc:
            if _absent(exc):
                return False
            raise
        return True
