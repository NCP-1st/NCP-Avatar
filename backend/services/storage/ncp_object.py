"""Naver Cloud Object Storage adapter."""

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
        self._access_key = config["access_key"]
        self._secret_key = config["secret_key"]
        self._bucket = config["bucket"]
        self._endpoint = config["endpoint"].rstrip("/")
        self._region = config.get("region", "kr-standard")
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if not self._access_key:
            raise ValueError("NCP Object Storage access key is required")
        if not self._secret_key:
            raise ValueError("NCP Object Storage secret key is required")
        if not self._bucket:
            raise ValueError("NCP Object Storage bucket is required")
        if not self._endpoint:
            raise ValueError("NCP Object Storage endpoint is required")

        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                ),
            )

        return self._client

    async def upload(
        self,
        data: bytes,
        *,
        object_name: str,
        mime_type: str,
    ) -> StoredObject:
        if not data:
            raise ValueError("cannot upload an empty object")
        if not object_name:
            raise ValueError("object name is required")

        def put_object() -> None:
            response = self._get_client().put_object(
                Bucket=self._bucket,
                Key=object_name,
                Body=data,
                ContentLength=len(data),
                ContentType=mime_type,
            )
            status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code != 200:
                raise RuntimeError(
                    f"NCP Object Storage upload returned HTTP {status_code}"
                )

        await asyncio.to_thread(put_object)

        content_hash = hashlib.sha256(data).hexdigest()
        encoded_key = quote(object_name, safe="/")

        return StoredObject(
            url=f"{self._endpoint}/{self._bucket}/{encoded_key}",
            object_key=object_name,
            content_hash=content_hash,
            size_bytes=len(data),
            mime_type=mime_type,
        )

    async def download(self, *, object_name: str) -> bytes:
        if not object_name:
            raise ValueError("object name is required")

        def get_object() -> bytes:
            response = self._get_client().get_object(
                Bucket=self._bucket,
                Key=object_name,
            )
            body = response["Body"]
            try:
                data = body.read()
            finally:
                body.close()
            if not data:
                raise RuntimeError("NCP Object Storage returned an empty object")
            return data

        return await asyncio.to_thread(get_object)

    async def delete(self, *, object_name: str) -> None:
        if not object_name:
            raise ValueError("object name is required")

        def delete_object() -> None:
            response = self._get_client().delete_object(
                Bucket=self._bucket,
                Key=object_name,
            )
            status_code = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code not in {200, 204}:
                raise RuntimeError(
                    f"NCP Object Storage delete returned HTTP {status_code}"
                )

        await asyncio.to_thread(delete_object)
