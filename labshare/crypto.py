"""AES-256-GCM encryption. The key is derived from the LABSHARE_SECRET env var."""
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def derive(secret: str, purpose: str) -> bytes:
    return hashlib.sha256(f"labshare-{purpose}:{secret}".encode()).digest()


class Vault:
    def __init__(self, secret: str):
        self.aes = AESGCM(derive(secret, "encryption"))

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + self.aes.encrypt(nonce, data, None)

    def decrypt(self, blob: bytes) -> bytes:
        return self.aes.decrypt(blob[:12], blob[12:], None)
