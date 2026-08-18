"""
One-off script to generate a VAPID key pair for Web Push (spec 6.3).

Usage:
    python backend/scripts/generate_vapid_keys.py

Prints private/public keys in the base64url format pywebpush and
browsers' PushManager.subscribe({applicationServerKey}) expect. Paste
them into your .env — never commit the private key to git.
"""
import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

    return _b64url(private_raw), _b64url(public_raw)


if __name__ == "__main__":
    priv, pub = generate()
    print("Add these to your .env file:\n")
    print(f"VAPID_PRIVATE_KEY={priv}")
    print(f"VAPID_PUBLIC_KEY={pub}")
    print("VAPID_CLAIMS_EMAIL=mailto:you@example.com")
