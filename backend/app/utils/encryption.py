from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class FernetEncryption:
    def __init__(self) -> None:
        key = get_settings().FERNET_KEY
        if not key:
            raise RuntimeError("FERNET_KEY is not configured — run scripts/generate_keys.py")
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        return self._fernet.decrypt(ciphertext).decode()


# Module-level singleton — instantiated lazily on first use
_encryption: FernetEncryption | None = None


def get_encryption() -> FernetEncryption:
    global _encryption
    if _encryption is None:
        _encryption = FernetEncryption()
    return _encryption
