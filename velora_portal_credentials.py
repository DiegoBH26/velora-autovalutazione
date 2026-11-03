"""Windows-only credential storage for Velora OTA agents.

Credentials NEVER enter source files, exported properties, reports or logs.
Only the loopback local agent can request Credential Manager operations.
Windows encrypts generic credentials for the signed-in Windows user.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168
MAX_SECRET_BYTES = 2500
ALLOWED_PORTALS = frozenset({"expedia", "vrbo", "holidu"})


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsPortalVault:
    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Il salvataggio protetto delle credenziali OTA richiede Windows.")
        self.api = ctypes.WinDLL("Advapi32", use_last_error=True)
        self.write = self.api.CredWriteW
        self.write.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
        self.write.restype = wintypes.BOOL
        self.read = self.api.CredReadW
        self.read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
        self.read.restype = wintypes.BOOL
        self.delete = self.api.CredDeleteW
        self.delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.delete.restype = wintypes.BOOL
        self.free = self.api.CredFree
        self.free.argtypes = [ctypes.c_void_p]
        self.free.restype = None

    @staticmethod
    def target(portal: str) -> str:
        if portal not in ALLOWED_PORTALS:
            raise ValueError("Portale non autorizzato.")
        return "Velora/OTA/" + portal

    def save(self, portal: str, email: str, password: str) -> None:
        name = self.target(portal)
        email = str(email or "").strip()
        if not email or "@" not in email or len(email) > 254:
            raise ValueError("Inserisci un indirizzo email valido.")
        password = str(password or "")
        encoded = password.encode("utf-16-le")
        if len(encoded) > MAX_SECRET_BYTES:
            raise ValueError("Password troppo lunga.")
        buffer = ctypes.create_string_buffer(encoded or b"\x00")
        record = _CREDENTIALW()
        record.Type = CRED_TYPE_GENERIC
        record.TargetName = name
        record.Comment = "Velora OTA - credenziale locale, mai pubblicata"
        record.CredentialBlobSize = len(encoded)
        record.CredentialBlob = (ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
                                 if encoded else ctypes.POINTER(ctypes.c_ubyte)())
        record.Persist = CRED_PERSIST_LOCAL_MACHINE
        record.UserName = email
        if not self.write(ctypes.byref(record), 0):
            raise OSError(ctypes.get_last_error(), "Impossibile salvare nel Gestore credenziali Windows.")

    def load(self, portal: str) -> tuple[str, str] | None:
        record = ctypes.POINTER(_CREDENTIALW)()
        if not self.read(self.target(portal), CRED_TYPE_GENERIC, 0, ctypes.byref(record)):
            error = ctypes.get_last_error()
            if error == ERROR_NOT_FOUND:
                return None
            raise OSError(error, "Impossibile leggere le credenziali protette.")
        try:
            item = record.contents
            if item.CredentialBlobSize and item.CredentialBlob:
                raw = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
                password = raw.decode("utf-16-le")
            else:
                password = ""
            return (item.UserName or "", password)
        finally:
            self.free(ctypes.cast(record, ctypes.c_void_p))

    def saved_email(self, portal: str) -> str | None:
        """Read only the Windows Credential Manager username, never its password.

        This endpoint is used to display the exact account saved on this PC.
        The credential blob is deliberately not copied or decoded.
        """
        record = ctypes.POINTER(_CREDENTIALW)()
        if not self.read(self.target(portal), CRED_TYPE_GENERIC, 0, ctypes.byref(record)):
            error = ctypes.get_last_error()
            if error == ERROR_NOT_FOUND:
                return None
            raise OSError(error, "Impossibile verificare l'email nel Gestore credenziali Windows.")
        try:
            return record.contents.UserName or ""
        finally:
            self.free(ctypes.cast(record, ctypes.c_void_p))

    def exists(self, portal: str) -> bool:
        return self.load(portal) is not None

    def remove(self, portal: str) -> None:
        if not self.delete(self.target(portal), CRED_TYPE_GENERIC, 0):
            error = ctypes.get_last_error()
            if error != ERROR_NOT_FOUND:
                raise OSError(error, "Impossibile cancellare le credenziali Windows.")


__all__ = ["WindowsPortalVault", "ALLOWED_PORTALS"]
