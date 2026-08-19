from __future__ import annotations

from endeavour_gpo.credentials import decrypt_cpassword, encrypt_cpassword


def test_cpassword_roundtrip():
    for plaintext in ("test", "Local*P4ssword!", ""):
        encrypted = encrypt_cpassword(plaintext)
        if not plaintext:
            assert encrypted == ""
            assert decrypt_cpassword("") == ""
            continue
        assert decrypt_cpassword(encrypted) == plaintext
