"""GitHub tokens of the deployment, kept encrypted and refreshed before they expire."""

import datetime
import json
import threading

import threadvault.encryption
import threadvault.github.oauth
import threadvault.storage

EXPIRY_MARGIN = datetime.timedelta(minutes = 5)

_TOKENS_SELECT = 'SELECT credential_data FROM github WHERE credential_id = 1'
_TOKENS_DELETE = 'DELETE FROM github WHERE credential_id = 1'

_TOKENS_UPSERT = """
    INSERT INTO github (credential_id, credential_data, update_time)
    VALUES (1, ?, ?)
    ON CONFLICT (credential_id) DO UPDATE SET
        credential_data = excluded.credential_data,
        update_time = excluded.update_time
"""

class TokenError(Exception):

    """Raised when there is no usable GitHub token, so that GitHub must be connected again."""

class TokenManager:

    """GitHub tokens in the database, encrypted there and refreshed one at a time.

    A refresh token works only once, so only one thread refreshes at a time,
    and the new pair is saved before it is used.
    """

    _LOCK = threading.Lock()

    def __init__(
        self,
        database: threadvault.storage.Database,
        cipher: threadvault.encryption.SecretCipher,
        client_id: str
    ) -> None:

        """Initialises the manager.

        Args:
            database: The database that holds the tokens.
            cipher: Cipher that encrypts the tokens in the database.
            client_id: Client ID of the GitHub App, which refreshes the tokens.
        """

        self._database = database
        self._cipher = cipher
        self._client_id = client_id

    def save(
        self,
        tokens: threadvault.github.oauth.Tokens
    ) -> None:

        """Saves tokens, replacing the earlier ones.

        Args:
            tokens: Tokens from the device flow or a refresh.
        """

        data = json.dumps({'access_token': tokens.access_token, 'access_expiry': tokens.access_expiry.isoformat(), 'refresh_token': tokens.refresh_token, 'refresh_expiry': tokens.refresh_expiry.isoformat()}, sort_keys = True)
        update_time = datetime.datetime.now(datetime.UTC).isoformat()

        with self._database.begin() as connection: connection.execute(_TOKENS_UPSERT, (self._cipher.encrypt(data), update_time))

    def acquire(
        self,
        now: datetime.datetime
    ) -> str:

        """Gives an access token, refreshing the pair when it expires within `EXPIRY_MARGIN`.

        Args:
            now: The current time.

        Returns:
            The access token.

        Raises:
            TokenError: GitHub is not connected, the refresh token has
                        expired, or the refresh failed.
            threadvault.encryption.SecretKeyError: The tokens cannot be decrypted.
        """

        with self._LOCK:

            tokens = self._load()

            if now < tokens.access_expiry - EXPIRY_MARGIN: return tokens.access_token
            if tokens.refresh_expiry <= now: raise TokenError('The GitHub connection has expired; connect GitHub again')

            try: tokens = threadvault.github.oauth.refresh(self._client_id, tokens.refresh_token)
            except threadvault.github.oauth.OAuthError as error: raise TokenError(f'The GitHub token could not be refreshed: {error}') from error

            self.save(tokens)

        return tokens.access_token

    def delete(
        self
    ) -> None:

        """Deletes the tokens, so that GitHub is no longer connected.

        A refresh that is under way finishes first, so that its new pair is
        deleted too rather than saved afterwards. GitHub keeps the
        authorisation until the user revokes it on GitHub.
        """

        with self._LOCK, self._database.begin() as connection: connection.execute(_TOKENS_DELETE)

    def connected(
        self
    ) -> bool:

        """Tells whether GitHub is connected, without asking GitHub.

        Returns:
            Whether tokens are saved, usable or not.
        """

        return self._database.connect().execute(_TOKENS_SELECT).fetchone() is not None

    def _load(
        self
    ) -> threadvault.github.oauth.Tokens:

        row = self._database.connect().execute(_TOKENS_SELECT).fetchone()

        if row is None: raise TokenError('GitHub is not connected yet')

        data = json.loads(self._cipher.decrypt(row['credential_data']))

        return threadvault.github.oauth.Tokens(access_token = data['access_token'], access_expiry = datetime.datetime.fromisoformat(data['access_expiry']), refresh_token = data['refresh_token'], refresh_expiry = datetime.datetime.fromisoformat(data['refresh_expiry']))
