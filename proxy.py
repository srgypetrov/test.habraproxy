import gzip
import logging
import re
import socket
import socketserver
import ssl

from collections import UserDict
from contextlib import contextmanager
from copy import copy


LOCAL_ADDR = ('localhost', 9090)
TARGET_ADDR = ('habrahabr.ru', 443)


class ResponseError(Exception):
    pass


class Headers(UserDict):

    def __init__(self, headers_list):
        super().__init__()
        for line in headers_list:
            line = line.decode('utf8')
            if ':' in line:
                key, value = line.split(':', maxsplit=1)
                self[key] = value.strip()
            else:
                self['general'] = line.strip()

    def __bytes__(self):
        lines = []
        for key, value in self.items():
            if key == 'general':
                line = value
            else:
                line = '{}: {}'.format(key, value)
            lines.append(line)
        lines.append('\r\n')
        return '\r\n'.join(lines).encode('utf8')

    @classmethod
    def from_rfile(cls, rfile):
        header_list = []
        while True:
            received = rfile.readline()
            if not received or received == b'\r\n':
                break
            header_list.append(received)
        return cls(header_list)


class Request(object):

    def __init__(self, request_headers):
        self.headers = copy(request_headers)
        self.headers['Host'] = TARGET_ADDR[0]

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

    @contextmanager
    @staticmethod
    def get_rfile():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = ssl.wrap_socket(sock, ssl_version=ssl.PROTOCOL_TLSv1)
        ssl_sock.connect(TARGET_ADDR)
        rfile = ssl_sock.makefile('rb')
        wfile = socketserver._SocketWriter(ssl_sock)
        yield rfile, wfile
        rfile.close()
        wfile.close()
        ssl_sock.close()


class Response(object):

    def __init__(self, headers, data=None, chunks_count=0):
        self.headers = headers
        self.packed_data = data
        self.chunks_count = chunks_count
        self.unpack_data()
        self._data = None

    def __iter__(self):
        yield bytes(self.headers)
        if self.is_chunked():
            for chunk in self.get_chunks():
                yield chunk
        elif self.packed_data is not None:
            yield self.packed_data

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self.pack_data()

    def get_chunk(self, part_slice):
        chunk_data = self.packed_data[part_slice]
        chunk_len = format(len(chunk_data), 'x').encode('utf8')
        return b'%s\r\n%s\r\n' % (chunk_len, chunk_data)

    def get_chunks(self):
        if self.is_chunked():
            chunk_size = int(len(self.packed_data) / self.chunks_count)
            for i in range(0, len(self.packed_data), chunk_size):
                if len(self.packed_data[i:]) < chunk_size * 1.5:
                    yield self.get_chunk(slice(i, None))
                    break
                yield self.get_chunk(slice(i, i + chunk_size))
            yield b'0\r\n\r\n'
        else:
            raise ResponseError('Content not chunked')

    def is_chunked(self):
        chunked = self.headers.get('Transfer-Encoding') == 'chunked'
        return chunked and self.packed_data is not None

    def is_gzipped_html(self):
        gzipped = self.headers.get('Content-Encoding') == 'gzip'
        is_html = self.headers.get('Content-Type') == 'text/html; charset=UTF-8'
        return gzipped and is_html and self.packed_data is not None

    def pack_data(self):
        if self.is_chunked() and self.is_gzipped_html():
            self.packed_data = gzip.compress(self.data.encode('utf8'))

    def unpack_data(self):
        if self.is_chunked() and self.is_gzipped_html():
            data = gzip.decompress(self.packed_data)
            self._data = data.decode('utf8')


class ProxyHandler(socketserver.StreamRequestHandler):

    def handle(self):
        headers = Headers.from_rfile(self.rfile)
        if headers:
            request = Request(headers)
            logging.debug(request.headers['general'])
            response = request.make_request()
            logging.debug(response.headers['general'])
            if response.is_gzipped_html():
                response.data = self.modify_data(response.data)
            for chunk in response:
                self.wfile.write(chunk)

    def modify_data(self, data):
        data = self.fix_links(data)
        data = self.wrap_words(data)
        return data

    @staticmethod
    def fix_links(data):
        link = '{}://{}'.format(socket.getservbyport(TARGET_ADDR[1]), TARGET_ADDR[0])
        pattern = r'(<[^<>]*)({})([^<>]*>)'.format(re.escape(link))
        repl = r'\g<1>http://{}:{}\g<3>'.format(*LOCAL_ADDR)
        return re.sub(pattern, repl, data, flags=re.I)

    def wrap_words(self, data):
        # re.sub(b'>([^<>\s]{6})<', 'repl', 'string')
        return data


def main():
    server = socketserver.TCPServer(LOCAL_ADDR, ProxyHandler)
    logging.basicConfig(
        format='%(message)s | %(asctime)s | %(levelname)s',
        level=logging.DEBUG,
        handlers=[logging.StreamHandler()]
    )
    print('Starting proxy server at http://{}:{}/'.format(*LOCAL_ADDR),
          'Quit the server with CONTROL-C.', sep='\n', end='\n\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
