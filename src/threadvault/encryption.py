"""Encryption for secrets kept on disk, such as GitHub tokens."""

import os
import pathlib

import cryptography.fernet

import threadvault.product

KEY_FILE = 'secret.key'

class SecretKeyError(Exception):

    """Raised when the secret key is invalid or cannot decrypt stored data."""

def generate() -> str:

    """Returns a new random key suitable for THREADVAULT_SECRET_KEY."""

    return cryptography.fernet.Fernet.generate_key().decode('ascii')

def load(
    secret_key: str | None,
    data_directory: pathlib.Path
) -> bytes:

    """Returns the configured key or the key file in the data directory.

    The key file is created with owner-only permissions the first time it is
    needed.

    Args:
        secret_key: Key from THREADVAULT_SECRET_KEY, or None when it is unset.
        data_directory: Directory that holds the key file.

    Returns:
        The key, ready to pass to `SecretCipher`.

    Raises:
        SecretKeyError: The configured key or the key file is not a valid key.
    """

    if secret_key: return _validate(secret_key, 'THREADVAULT_SECRET_KEY')

    file = pathlib.Path(os.path.join(data_directory, KEY_FILE))
    if not file.exists(): _create(file)

    key = file.read_text(encoding = 'ascii').strip()

    return _validate(key, str(file))

class SecretCipher:

    """Encrypts and decrypts text with a Fernet key."""

    def __init__(
        self,
        key: bytes
    ) -> None:

        """Initialises the cipher.

        Args:
            key: Key returned by `load`.
        """

        self._fernet = cryptography.fernet.Fernet(key)

    def encrypt(
        self,
        text: str
    ) -> str:

        """Encrypts text.

        Args:
            text: Text to encrypt.

        Returns:
            The ciphertext as URL-safe base64 text.
        """

        return self._fernet.encrypt(text.encode('utf-8')).decode('ascii')

    def decrypt(
        self,
        text: str
    ) -> str:

        """Decrypts text produced by `encrypt`.

        Args:
            text: Text returned by `encrypt`.

        Returns:
            The original text.

        Raises:
            SecretKeyError: The text was encrypted with another key or has been altered.
        """

        try: return self._fernet.decrypt(text).decode('utf-8')
        except cryptography.fernet.InvalidToken: raise SecretKeyError('Stored secrets cannot be decrypted; the secret key may have changed') from None

def _validate(
    key: str,
    source: str
) -> bytes:

    try: cryptography.fernet.Fernet(key)
    except ValueError: raise SecretKeyError(f"{source} does not hold a valid key; create one with '{threadvault.product.COMMAND} key'") from None

    return key.encode('ascii')

def _create(
    path: pathlib.Path
) -> None:

    path.parent.mkdir(mode = 0o700, parents = True, exist_ok = True)

    try: descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError: return

    with os.fdopen(descriptor, 'w', encoding = 'ascii') as stream: stream.write(generate() + '\n')
