"""SecretManager interface and the local envelope-encryption backend.

Each secret gets a random 256-bit data key. The value is sealed with AES-256-GCM under the
data key; the data key is sealed with AES-256-GCM under the master key. Rotating the
master key only re-wraps data keys. Vault/AWS/GCP/Azure backends implement the same
Protocol and are selected by configuration.
"""

from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.core.redaction import redactor
from app.core.time import utcnow
from app.models import Secret

SECRET_REF_PREFIX = "secret:"


def make_ref(secret_id: uuid.UUID) -> str:
    return f"{SECRET_REF_PREFIX}{secret_id}"


def parse_ref(ref: str) -> uuid.UUID:
    if not ref.startswith(SECRET_REF_PREFIX):
        raise AppError("Invalid secret reference", code=ErrorCode.secret_not_found)
    try:
        return uuid.UUID(ref.removeprefix(SECRET_REF_PREFIX))
    except ValueError as exc:
        raise AppError("Invalid secret reference", code=ErrorCode.secret_not_found) from exc


def hint_for(value: str) -> str:
    return f"…{value[-4:]}" if len(value) >= 8 else "…"


@dataclass(frozen=True)
class SecretMeta:
    id: uuid.UUID
    ref: str
    name: str
    hint: str
    version: int


class SecretManager(Protocol):
    async def put(
        self, session: AsyncSession, workspace_id: uuid.UUID, name: str, value: str, *,
        description: str | None = None, managed: bool = False,
    ) -> SecretMeta: ...
    async def get(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str) -> str: ...
    async def rotate(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str, value: str) -> SecretMeta: ...
    async def delete(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str) -> None: ...


class LocalEnvelopeSecretManager:
    def __init__(self, master_key_b64: str) -> None:
        key = base64.b64decode(master_key_b64)
        if len(key) != 32:
            raise ValueError("SECRETS_MASTER_KEY must decode to exactly 32 bytes")
        self._master = AESGCM(key)

    def _seal(self, value: str) -> tuple[bytes, bytes, bytes, bytes]:
        data_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ciphertext = AESGCM(data_key).encrypt(nonce, value.encode(), None)
        key_nonce = os.urandom(12)
        wrapped = self._master.encrypt(key_nonce, data_key, b"data-key")
        return ciphertext, nonce, wrapped, key_nonce

    def _open(self, row: Secret) -> str:
        data_key = self._master.decrypt(row.key_nonce, row.wrapped_data_key, b"data-key")
        return AESGCM(data_key).decrypt(row.nonce, row.ciphertext, None).decode()

    async def _row(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str) -> Secret:
        row = await session.scalar(
            select(Secret).where(Secret.id == parse_ref(ref), Secret.workspace_id == workspace_id)
        )
        if row is None:
            raise AppError("Secret not found", code=ErrorCode.secret_not_found)
        return row

    async def put(
        self, session: AsyncSession, workspace_id: uuid.UUID, name: str, value: str, *,
        description: str | None = None, managed: bool = False,
    ) -> SecretMeta:
        ciphertext, nonce, wrapped, key_nonce = self._seal(value)
        existing = await session.scalar(
            select(Secret).where(Secret.workspace_id == workspace_id, Secret.name == name)
        )
        if existing is not None:
            existing.ciphertext, existing.nonce = ciphertext, nonce
            existing.wrapped_data_key, existing.key_nonce = wrapped, key_nonce
            existing.hint = hint_for(value)
            existing.version += 1
            existing.rotated_at = utcnow()
            if description is not None:
                existing.description = description
            row = existing
        else:
            row = Secret(
                workspace_id=workspace_id, name=name, description=description,
                ciphertext=ciphertext, nonce=nonce, wrapped_data_key=wrapped,
                key_nonce=key_nonce, hint=hint_for(value), managed=managed,
            )
            session.add(row)
        await session.flush()
        return SecretMeta(row.id, make_ref(row.id), row.name, row.hint, row.version)

    async def get(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str) -> str:
        value = self._open(await self._row(session, workspace_id, ref))
        redactor.register(value)
        return value

    async def rotate(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str, value: str) -> SecretMeta:
        row = await self._row(session, workspace_id, ref)
        return await self.put(session, workspace_id, row.name, value)

    async def delete(self, session: AsyncSession, workspace_id: uuid.UUID, ref: str) -> None:
        row = await self._row(session, workspace_id, ref)
        await session.delete(row)
        await session.flush()


_manager: SecretManager | None = None


def get_secret_manager() -> SecretManager:
    global _manager
    if _manager is None:
        _manager = LocalEnvelopeSecretManager(get_settings().secrets_master_key.get_secret_value())
    return _manager
