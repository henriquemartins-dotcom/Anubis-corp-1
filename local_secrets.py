from __future__ import annotations

import base64
import ctypes
import sys

if sys.platform == "win32":
    from ctypes import wintypes


def protect_local_secret(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.encode("utf-8")
    if sys.platform != "win32":
        return "plain:" + base64.urlsafe_b64encode(raw).decode("ascii")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(raw)
    input_blob = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return "dpapi:" + base64.urlsafe_b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def unprotect_local_secret(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith("plain:"):
        return base64.urlsafe_b64decode(value[6:].encode("ascii")).decode("utf-8")
    if not value.startswith("dpapi:"):
        return value
    if sys.platform != "win32":
        return ""

    encrypted = base64.urlsafe_b64decode(value[6:].encode("ascii"))

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(encrypted)
    input_blob = DataBlob(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)
