# SPDX-FileCopyrightText: 2026 Mahiro Sakaue
# SPDX-License-Identifier: MIT

"""Short links on this computer that redirect to the long addresses of the pages that setup shows."""

import collections.abc
import logging
import threading
import typing
import wsgiref.simple_server
import wsgiref.types

HOST = '127.0.0.1'
POLL_INTERVAL = 0.05

_LOGGER = logging.getLogger(__name__)

class Shortener:

    """Serves short links on the loopback interface of this computer while it is open.

    A short link answers a browser on this computer with a redirect to its
    long address, so that a terminal can show the short link instead.

    Attributes:
        failure: Why the server could not listen, or None when it serves.
    """

    def __init__(self) -> None:

        """Listens on a free port of the loopback interface, when this computer allows it."""

        self.failure = None
        self._addresses = {}
        self._server: wsgiref.simple_server.WSGIServer | None = None

        try: self._server = wsgiref.simple_server.make_server(HOST, 0, self._redirect, handler_class = _Handler)
        except OSError as error: self.failure = error

    def __enter__(self) -> typing.Self:

        """Starts serving the short links.

        Returns:
            This shortener.
        """

        if self._server is not None: threading.Thread(target = self._server.serve_forever, kwargs = {'poll_interval': POLL_INTERVAL}, daemon = True).start()

        return self

    def __exit__(
        self,
        *_: object
    ) -> None:

        """Stops serving the short links and frees the port."""

        if self._server is not None: self._server.shutdown(); self._server.server_close()

    def shorten(
        self,
        name: str,
        address: str
    ) -> str:

        """Returns a short link that redirects to an address.

        Args:
            name: Path of the short link, such as slack.
            address: Long address to redirect to.

        Returns:
            The short link, or the address itself when the server could not
            listen.
        """

        if self._server is None: return address

        self._addresses[name] = address

        return f'http://{HOST}:{self._server.server_port}/{name}'

    def _redirect(
        self,
        environment: wsgiref.types.WSGIEnvironment,
        respond: wsgiref.types.StartResponse
    ) -> collections.abc.Iterable[bytes]:

        path: str = environment.get('PATH_INFO', '')
        address = self._addresses.get(path.removeprefix('/'))

        if address is None:

            respond('404 Not Found', [('Content-Type', 'text/plain; charset=utf-8')])

            return [b'Not found\n']

        respond('302 Found', [('Location', address)])

        return []

class _Handler(wsgiref.simple_server.WSGIRequestHandler):

    @typing.override
    def log_message(
        self,
        format: str,
        *args: object
    ) -> None:

        _LOGGER.debug(format, *args)
