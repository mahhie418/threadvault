import http.client
import logging
import re
import unittest.mock
import urllib.parse
import wsgiref.simple_server

import pytest

import threadvault.shortener

def fetch(
    link: str
) -> http.client.HTTPResponse:

    parts = urllib.parse.urlsplit(link)
    connection = http.client.HTTPConnection(parts.netloc, timeout = 10)

    try:

        connection.request('GET', parts.path)
        response = connection.getresponse()
        response.read()

    finally:

        connection.close()

    return response

def test_shortener_link_redirection(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture
) -> None:

    caplog.set_level(logging.DEBUG, logger = threadvault.shortener.__name__)

    with threadvault.shortener.Shortener() as shortener:

        link = shortener.shorten('xxx', 'https://xxx.example/?xxx=1&xxx=2')
        response = fetch(link)

    assert re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/xxx', link)
    assert (response.status, response.getheader('Location')) == (302, 'https://xxx.example/?xxx=1&xxx=2')
    assert capsys.readouterr() == ('', '')
    assert [(record.levelname, record.getMessage()) for record in caplog.records] == [('DEBUG', '"GET /xxx HTTP/1.1" 302 0')]

def test_shortener_link_absence() -> None:

    with threadvault.shortener.Shortener() as shortener: response = fetch(shortener.shorten('xxx1', 'https://xxx.example/').replace('/xxx1', '/xxx2'))

    assert response.status == 404

def test_shortener_server_failure(
    monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr(wsgiref.simple_server, 'make_server', unittest.mock.Mock(side_effect = OSError('xxx')))

    with threadvault.shortener.Shortener() as shortener: link = shortener.shorten('xxx', 'https://xxx.example/')

    assert str(shortener.failure) == 'xxx'
    assert link == 'https://xxx.example/'

def test_shortener_server_stop() -> None:

    with threadvault.shortener.Shortener() as shortener: link = shortener.shorten('xxx', 'https://xxx.example/')

    with pytest.raises(ConnectionRefusedError): fetch(link)
