"""离线测试的网络隔离契约。"""
import socket

import curl_cffi.requests as curl_requests
import pytest


def test_external_dns_is_blocked_by_default():
    with pytest.raises(RuntimeError, match="pytest.mark.network"):
        socket.getaddrinfo("example.com", 443)


def test_external_socket_is_blocked_by_default():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(RuntimeError, match="pytest.mark.network"):
            client.connect(("192.0.2.1", 443))


def test_curl_cffi_external_request_is_blocked_by_default():
    with curl_requests.Session() as session:
        with pytest.raises(RuntimeError, match="pytest.mark.network"):
            session.get("https://example.com")


def test_localhost_socket_is_allowed():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        with socket.create_connection(listener.getsockname(), timeout=1) as client:
            connection, _ = listener.accept()
            with connection:
                client.sendall(b"ok")
                assert connection.recv(2) == b"ok"
