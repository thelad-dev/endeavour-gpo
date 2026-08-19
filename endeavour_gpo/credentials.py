"""Decrypt legacy GPP cpassword fields (MS-GPPREF static AES key)."""

from __future__ import annotations

import base64

from Crypto.Cipher import AES

GPP_AES_KEY = bytes(
    [
        0x4E,
        0x99,
        0x06,
        0xE8,
        0xFC,
        0xB6,
        0x6C,
        0xC9,
        0xFA,
        0xF4,
        0x93,
        0x10,
        0x62,
        0x0F,
        0xFE,
        0xE8,
        0xF4,
        0x96,
        0xE8,
        0x06,
        0xCC,
        0x05,
        0x79,
        0x90,
        0x20,
        0x9B,
        0x09,
        0xA4,
        0x33,
        0xB6,
        0x6C,
        0x1B,
    ]
)
GPP_AES_IV = b"\x00" * 16


def decrypt_cpassword(cpassword: str) -> str:
    if not cpassword:
        return ""
    padded = cpassword + "=" * (-len(cpassword) % 4)
    raw = AES.new(GPP_AES_KEY, AES.MODE_CBC, GPP_AES_IV).decrypt(base64.b64decode(padded))
    return raw.decode("utf-16-le").rstrip("\x00")


def encrypt_cpassword(plaintext: str) -> str:
    if not plaintext:
        return ""
    data = plaintext.encode("utf-16-le")
    pad_len = (16 - (len(data) % 16)) % 16
    data += b"\x00" * pad_len
    encrypted = AES.new(GPP_AES_KEY, AES.MODE_CBC, GPP_AES_IV).encrypt(data)
    return base64.b64encode(encrypted).decode("ascii").rstrip("=")
