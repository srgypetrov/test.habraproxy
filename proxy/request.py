import socket
import socketserver
import ssl
from contextlib import contextmanager
from copy import copy

from .headers import Headers
from .response import Response
from .settings import settings


class Request(object):

    def __init__(self, request_headers):
        self.headers = copy(request_headers)
        self.headers['Host'] = settings.target_addr[0]

    @staticmethod
    def get_data(response_headers, rfile):
        length = int(response_headers['Content-Length'])
        data = rfile.read(length)
        return Response(response_headers, data)

    def get_chunked_data(self, response_headers, rfile):
        chunks = []
        chunk_size = self.get_chunk_size(rfile)
        while chunk_size:
            chunk = rfile.read(chunk_size)
            chunks.append(chunk)
            chunk_size = self.get_chunk_size(rfile)
        return Response(response_headers, b''.join(chunks), len(chunks))

    @staticmethod
    def get_chunk_size(rfile):
        hex_chunk_size = rfile.readline()
        if hex_chunk_size == b'\r\n':
            hex_chunk_size = rfile.readline()
        return int(hex_chunk_size.strip(), 16)

    def make_request(self):
        with self.get_rfile() as (rfile, wfile):
            wfile.write(bytes(self.headers))
            response_headers = Headers.from_rfile(rfile)
            if 'Content-Length' in response_headers:
                return self.get_data(response_headers, rfile)
            elif 'Transfer-Encoding' in response_headers:
                return self.get_chunked_data(response_headers, rfile)
            return Response(response_headers)

    @staticmethod
    @contextmanager
    def get_rfile():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = ssl.wrap_socket(sock, ssl_version=ssl.PROTOCOL_TLSv1)
        ssl_sock.connect(settings.target_addr)
        rfile = ssl_sock.makefile('rb')
        wfile = socketserver._SocketWriter(ssl_sock)
        yield rfile, wfile
        rfile.close()
        wfile.close()
        ssl_sock.close()

    @property
    def path(self):
        general = self.headers['general'].split()
        return general[1]
