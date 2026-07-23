"""Encrypt/decrypt bull-bear valuations so they can live in the PUBLIC dashboard
repo as ciphertext while the plaintext stays private.

Model:
  - A Fernet key lives in `valuations_key.txt` (gitignored, private repo) and in
    the hosted dashboard's Streamlit secret `valuations_key`. Set once, static.
  - `encrypt_to()` writes `valuations.enc` (ciphertext) + `valuations.enc.sha`
    (hash of the plaintext) — but ONLY re-encrypts when the plaintext changed,
    so an unchanged run produces no git diff ("only when necessary").
  - The dashboard reads `valuations.enc` and decrypts with the secret key.

Only bull/bear values are encrypted — the `note` reasoning is dropped entirely.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
KEY_FILE = HERE / "valuations_key.txt"
SRC = HERE / "valuations.json"


def _key() -> bytes | None:
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip().encode()
    return None


def _bull_bear_only(data: dict) -> dict:
    """Strip to {ticker: {bull, bear}} — never encrypt the reasoning notes."""
    return {k: {"bull": v.get("bull"), "bear": v.get("bear")}
            for k, v in data.items() if not k.startswith("_")}


def _plaintext_bytes() -> bytes:
    data = json.loads(SRC.read_text()) if SRC.exists() else {}
    return json.dumps(_bull_bear_only(data), sort_keys=True, separators=(",", ":")).encode()


def encrypt_to(dest_dir: Path) -> bool:
    """Write valuations.enc + .sha into dest_dir. Returns True if it changed
    (i.e. a re-encrypt happened), False if the plaintext was unchanged."""
    from cryptography.fernet import Fernet
    key = _key()
    if not key:
        raise RuntimeError(f"No key at {KEY_FILE}. Run crypto_valuations.py --init first.")
    plaintext = _plaintext_bytes()
    digest = hashlib.sha256(plaintext).hexdigest()
    sha_file = dest_dir / "valuations.enc.sha"
    if sha_file.exists() and sha_file.read_text().strip() == digest:
        return False  # unchanged — no re-encrypt, no git diff
    token = Fernet(key).encrypt(plaintext)
    (dest_dir / "valuations.enc").write_bytes(token)
    sha_file.write_text(digest)
    return True


def decrypt(enc_path: Path, key: str) -> dict:
    """Decrypt valuations.enc with the given key string. {} on any failure."""
    from cryptography.fernet import Fernet
    try:
        token = enc_path.read_bytes()
        plaintext = Fernet(key.encode()).decrypt(token)
        return json.loads(plaintext)
    except Exception:
        return {}


if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        if KEY_FILE.exists():
            print(f"Key already exists at {KEY_FILE} — leaving it.")
        else:
            from cryptography.fernet import Fernet
            KEY_FILE.write_text(Fernet.generate_key().decode())
            print(f"Wrote new key to {KEY_FILE} (gitignored).")
    else:
        print("Usage: python crypto_valuations.py --init")
