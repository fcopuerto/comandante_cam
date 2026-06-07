"""
Run once at setup. Never commit the secrets/ directory.

Usage:
    python scripts/generate_keys.py

Outputs:
    secrets/rsa_private.pem  — RSA-2048 private key (JWT signing)
    secrets/rsa_public.pem   — RSA-2048 public key  (JWT verification)
    FERNET_KEY and SECRET_KEY printed to stdout — copy into .env
"""

import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SECRETS_DIR = Path(__file__).parent.parent / "secrets"


def generate_rsa_keypair() -> None:
    SECRETS_DIR.mkdir(exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path = SECRETS_DIR / "rsa_private.pem"
    public_path = SECRETS_DIR / "rsa_public.pem"
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    private_path.chmod(0o600)
    print(f"RSA private key → {private_path}")
    print(f"RSA public key  → {public_path}")


def main() -> None:
    generate_rsa_keypair()
    fernet_key = Fernet.generate_key().decode()
    secret_key = secrets.token_hex(32)
    print()
    print("Add these to your .env file:")
    print(f"FERNET_KEY={fernet_key}")
    print(f"SECRET_KEY={secret_key}")


if __name__ == "__main__":
    main()
