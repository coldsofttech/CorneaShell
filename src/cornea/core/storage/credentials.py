"""Secrets in Windows Credential Manager.

Each secret is a generic credential named ``Cornea/<app id>/<key>`` in the signed-in user's own
vault, which Windows encrypts for that user. Nothing is written to Cornea's files. A secret is
text of at most :data:`MAX_SECRET_BYTES` bytes (Credential Manager's own limit).
"""

import ctypes
import sys
from ctypes import wintypes
from typing import Protocol

from cornea.core.storage.database import check_key

MAX_SECRET_BYTES = 2560
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
_USER = "cornea"


class SecretsUnavailable(RuntimeError):
    """Credential Manager cannot be used here (not Windows, or the call failed)."""

    def __init__(self, message: str = "Secure storage is not available.") -> None:
        super().__init__(message)


class CredentialBackend(Protocol):
    """Where secrets live. Windows Credential Manager in use; a dictionary in tests."""

    def read(self, target: str) -> str | None: ...
    def write(self, target: str, value: str) -> None: ...
    def delete(self, target: str) -> bool: ...
    def names(self, prefix: str) -> list[str]: ...


class _Credential(ctypes.Structure):
    _fields_ = (
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    )


class WindowsCredentialBackend:
    """Windows Credential Manager through ``advapi32``."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise SecretsUnavailable("Secure storage only works on Windows for now.")
        self._advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.POINTER(_Credential)
        self._advapi.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(pointer),
        ]
        self._advapi.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        self._advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._advapi.CredEnumerateW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.POINTER(pointer)),
        ]
        self._advapi.CredFree.argtypes = [wintypes.LPVOID]

    def read(self, target: str) -> str | None:
        found = ctypes.POINTER(_Credential)()
        if not self._advapi.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(found)):
            self._fail("read", allow_missing=True)
            return None
        try:
            credential = found.contents
            data = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        finally:
            self._advapi.CredFree(found)
        return data.decode("utf-8")

    def write(self, target: str, value: str) -> None:
        data = value.encode("utf-8")
        blob = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        credential = _Credential()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(data)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = _USER
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            self._fail("write")

    def delete(self, target: str) -> bool:
        if self._advapi.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
            return True
        self._fail("delete", allow_missing=True)
        return False

    def names(self, prefix: str) -> list[str]:
        count = wintypes.DWORD(0)
        found = ctypes.POINTER(ctypes.POINTER(_Credential))()
        if not self._advapi.CredEnumerateW(
            prefix + "*", 0, ctypes.byref(count), ctypes.byref(found)
        ):
            self._fail("list", allow_missing=True)
            return []
        try:
            return [str(found[index].contents.TargetName) for index in range(count.value)]
        finally:
            self._advapi.CredFree(found)

    @staticmethod
    def _fail(action: str, *, allow_missing: bool = False) -> None:
        code = ctypes.get_last_error()
        if allow_missing and code == ERROR_NOT_FOUND:
            return
        raise SecretsUnavailable(f"Credential Manager could not {action} ({ctypes.WinError(code)})")


class SecretStore:
    """The secrets of one app: ``get``, ``set``, ``delete`` and ``keys``, all by text key.

    Example:
        >>> from cornea.core.storage.credentials import MemoryCredentials
        >>> secrets = SecretStore("com.example.notes", MemoryCredentials())
        >>> secrets.set("api-token", "s3cret")
        >>> secrets.get("api-token"), secrets.keys()
        ('s3cret', ['api-token'])
    """

    def __init__(self, app_id: str, backend: CredentialBackend | None = None) -> None:
        self._app_id = app_id
        self._backend = backend

    @property
    def _store(self) -> CredentialBackend:
        if self._backend is None:  # only now: importing and building need Windows
            self._backend = WindowsCredentialBackend()
        return self._backend

    @property
    def _prefix(self) -> str:
        return f"Cornea/{self._app_id}/"

    def get(self, key: str, default: str | None = None) -> str | None:
        """The secret, or ``default`` if there is none."""
        value = self._store.read(self._prefix + check_key(key))
        return default if value is None else value

    def set(self, key: str, value: str) -> None:
        """Save a secret, replacing any earlier one."""
        if not isinstance(value, str) or not value:
            raise ValueError("a secret must be a non-empty string")
        if len(value.encode("utf-8")) > MAX_SECRET_BYTES:
            raise ValueError(f"a secret may hold at most {MAX_SECRET_BYTES} bytes")
        self._store.write(self._prefix + check_key(key), value)

    def delete(self, key: str) -> bool:
        """Remove a secret. ``True`` if there was one."""
        return self._store.delete(self._prefix + check_key(key))

    def has(self, key: str) -> bool:
        """Whether a secret exists."""
        return self.get(key) is not None

    def keys(self) -> list[str]:
        """The keys of this app's secrets."""
        prefix = self._prefix
        return sorted(name[len(prefix) :] for name in self._store.names(prefix))


class MemoryCredentials:
    """Secrets kept in a dictionary, for tests and for systems without Credential Manager."""

    def __init__(self) -> None:
        self.entries: dict[str, str] = {}

    def read(self, target: str) -> str | None:
        return self.entries.get(target)

    def write(self, target: str, value: str) -> None:
        self.entries[target] = value

    def delete(self, target: str) -> bool:
        return self.entries.pop(target, None) is not None

    def names(self, prefix: str) -> list[str]:
        return [name for name in self.entries if name.startswith(prefix)]
