"""NAVER Cloud Object Storage adapter using the S3-compatible API."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import Config

from backend.services.storage.base import StorageAdapter, StoredObject


class NcpObjectStorageAdapter(StorageAdapter):
    def __init__(self, config: dict[str, Any]) -> None:
        self._bucket = config["bucket"]
        self._endpoint = config["endpoint"].rstrip("/")
        self._access_key = config["access_key"]
        self._secret_key = config["secret_key"]
        self._region = config.get("region", "kr-standard")
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if not self._endpoint:
            raise ValueError("NCP Object Storage endpoint is required")
        if not self._access_key or not self._secret_key:
            raise ValueError("NCP Object Storage credentials are required")
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
                config=Config(signature_version="s3v4"),
            )
        return self._client

    async def upload(
        self,
        data: bytes,
        *,
        object_name: str,
        mime_type: str,
    ) -> StoredObject:
        if not self._bucket:
            raise ValueError("NCP Object Storage bucket is required")
        if not data:
            raise ValueError("cannot upload an empty object")

        def put_object() -> None:
            self._get_client().put_object(
                Bucket=self._bucket,
                Key=object_name,
                Body=data,
                ContentType=mime_type,
            )

        await asyncio.to_thread(put_object)
        digest = hashlib.sha256(data).hexdigest()
        encoded_key = quote(object_name, safe="/")
        return StoredObject(
            url=f"{self._endpoint}/{self._bucket}/{encoded_key}",
            content_hash=digest,
            size_bytes=len(data),
            mime_type=mime_type,
            object_key=object_name,
        )
