import gzip
import logging
import re
import socket
import socketserver
import ssl

from collections import UserDict
from contextlib import contextmanager
from copy import copy


HOST, PORT = "localhost", 9090


class ChunkedResponseError(Exception):
    pass


class ChunkedResponse(object):

    def __init__(self, raw_content):
        try:
            self.raw_headers, self.raw_data = raw_content.strip().split(b'\r\n\r\n')
        except ValueError:
            raise ChunkedResponseError('Invalid content')
        self.headers = self.unpack_headers()
        self.clean_headers()
        self.data, self.chunks_count = self.unpack_data()

    def __iter__(self):
        yield self.raw_headers + b'\r\n\r\n'
        for chunk in self.get_chunks():
            yield chunk

    def clean_headers(self):
        transfer_encoding = self.headers.get('Transfer-Encoding')
        if transfer_encoding != 'chunked':
            raise ChunkedResponseError('Invalid Transfer-Encoding', transfer_encoding)

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self.pack_data()

    def get_chunks(self):
        chunk_size = int(len(self.packed_data) / self.chunks_count)
        for i in range(0, len(self.packed_data), chunk_size):
            chunk_data = self.packed_data[i:i + chunk_size]
            chunk_len = format(len(chunk_data), 'x').encode('utf8')
            yield b'%s\r\n%s\r\n' % (chunk_len, chunk_data)
        yield b'0\r\n\r\n'

    def pack_data(self):
        self.packed_data = self.data

    def unpack_data(self):
        patterns = [rb'\r\n[0-9A-F]+$', rb'\r\n[0-9A-F]+\r\n', rb'^[0-9A-F]+\r\n']
        data, count = re.subn(rb'|'.join(patterns), b'', self.raw_data, flags=re.I)
        return data, count

    def unpack_headers(self):
        headers = {}
        for line in self.raw_headers.decode('utf8').splitlines():
            if ':' in line:
                k, v = line.split(':', maxsplit=1)
                headers[k] = v.strip()
            else:
                headers[line] = None
        return headers


class HTMLChunkedResponse(ChunkedResponse):

    def clean_headers(self):
        super().clean_headers()
        content_encoding = self.headers.get('Content-Encoding')
        content_type = self.headers.get('Content-Type')
        if content_encoding != 'gzip':
            raise ChunkedResponseError('Invalid Content-Encoding', content_encoding)
        if content_type != 'text/html; charset=UTF-8':
            raise ChunkedResponseError('Invalid Content-Type', content_type)

    def pack_data(self):
        self.packed_data = gzip.compress(self.data.encode('utf8'))

    def unpack_data(self):
        compressed_data, count = super().unpack_data()
        data = gzip.decompress(compressed_data)
        return data.decode('utf8'), count


class Headers(UserDict):

    def __init__(self, headers_list):
        super().__init__()
        for line in headers_list:
            line = line.decode('utf8')
            if ':' in line:
                k, v = line.split(':', maxsplit=1)
                self[k] = v.strip()
            else:
                self['general'] = line

    @classmethod
    def from_rfile(cls, rfile):
        header_list = []
        while True:
            received = rfile.readline()
            if not received:
                break
            header_list.append(received)
            if received == b'\r\n':
                break
        return cls(header_list)


class Request(object):

    target_host = 'habrahabr.ru'

    def __init__(self, request_headers):
        self.headers = copy(request_headers)
        self.headers['Host'] = self.target_host

    def make_request(self):
        with self.get_rfile() as (rfile, wfile):
            wfile.write(self.headers)
            response_headers = Headers.from_rfile(rfile)
            if 'Content-Length' in response_headers:
                return self.get_data(response_headers, rfile)
            elif 'Transfer-Encoding' in response_headers:
                return self.get_chunked_data(response_headers, rfile)
            else:
                return Response(response_headers)

    @contextmanager
    def get_rfile(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = ssl.wrap_socket(sock, ssl_version=ssl.PROTOCOL_TLSv1)
        ssl_sock.connect((self.target_host, 443))
        rfile = ssl_sock.makefile('rb')
        wfile = ssl_sock.makefile('wb')
        yield rfile, wfile
        rfile.close()
        wfile.close()
        ssl_sock.close()


class Response(object):

    def __init__(self, headers, data=None):
        pass


class ProxyHandler(socketserver.StreamRequestHandler):

    # target_host = 'habrahabr.ru'
    # local_host = '{}:{}'.format(HOST, PORT)
    # bufsize = 2048

    # def continue_obtain(self, chunk):
    #     if b'\r\n0\r\n' in chunk:
    #         return False
    #     if chunk.endswith(b'\r\n\r\n'):
    #         if b'Content-Length' in chunk:
    #             return
    #         elif b'Transfer-Encoding' not in chunk:
    #             return False
    #     return True

    # def get_content(self, request_headers):
    #     chunks = []
    #     with self.get_rfile() as sock:
    #         sock.send(request_headers)
    #         obtaining = True
    #         while obtaining:
    #             received = sock.recv(self.bufsize)
    #             chunks.append(received)
    #             obtaining = self.continue_obtain(received)
    #     return b''.join(chunks)

    # def get_response(self, content):
    #     try:
    #         response = HTMLChunkedResponse(content)
    #     except ChunkedResponseError:
    #         try:
    #             response = ChunkedResponse(content)
    #         except ChunkedResponseError:
    #             response = [content]
    #     return response

    def handle(self):
        headers = Headers.from_rfile(self.rfile)
        if headers:
            request = Request(headers)
            logging.debug(request.headers['general'])
            response = request.make_request()
            logging.debug(response.headers['general'])

            # content = self.get_content(request_headers)
            # response = self.get_response(content)
            # for chunk in response:
            #     self.wfile.write(chunk)

    # def sdfsdf(self):
    #     re.sub(b'>([^<>\s]{6})<', 'repl', 'string')


if __name__ == "__main__":
    server = socketserver.TCPServer((HOST, PORT), ProxyHandler)
    logging.basicConfig(
        format='%(message)s | %(asctime)s | %(levelname)s',
        level=logging.DEBUG,
        handlers=[logging.StreamHandler()]
    )
    print('Starting proxy server at http://{}:{}/'.format(HOST, PORT),
          'Quit the server with CONTROL-C.', sep='\n', end='\n\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
