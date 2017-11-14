import gzip
import logging
import socket
import socketserver
import ssl

from collections import UserDict
from contextlib import contextmanager
from copy import copy
from html.parser import HTMLParser


LOCAL_ADDR = ('localhost', 9999)
TARGET_ADDR = ('habrahabr.ru', 443)


class ProxyHTMLParser(HTMLParser):

    def __init__(self, callbacks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_enabled = True
        self.starttag_end_index = 0
        self.callbacks = callbacks or {}

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.data_enabled = False
        if tag in self.callbacks:
            lineno, start_pos, end_pos = self.get_pos(with_end=True)
            self.callbacks[tag](attrs, lineno, start_pos, end_pos)

    def handle_data(self, data):
        if 'data' in self.callbacks and self.data_enabled and data.strip():
            lineno, start_pos = self.get_pos()
            self.callbacks['data'](data, lineno, start_pos)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.data_enabled = True

    def get_pos(self, with_end=False):
        lineno, start_pos = self.getpos()
        if with_end:
            line_index = self.rawdata.rindex('\n', 0, self.starttag_end_index) + 1
            end_pos = self.starttag_end_index - line_index
            return lineno, start_pos, end_pos
        return lineno, start_pos

    def parse_starttag(self, i):
        self.starttag_end_index = self.check_for_whole_start_tag(i)
        return super().parse_starttag(i)


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

    @staticmethod
    @contextmanager
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
        self._data = None
        self.headers = headers
        self.packed_data = data
        self.chunks_count = chunks_count
        self.unpack_data()

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
        if self.is_gzipped_html():
            self.packed_data = gzip.compress(self.data.encode('utf8'))

    def unpack_data(self):
        if self.is_gzipped_html():
            data = gzip.decompress(self.packed_data)
            self._data = data.decode('utf8')


class ProxyHandler(socketserver.StreamRequestHandler):

    def __init__(self, *args, **kwargs):
        self._html_data = None
        self._local_link = 'http://{}:{}'.format(*LOCAL_ADDR)
        self._target_link = '{}://{}'.format(socket.getservbyport(
            TARGET_ADDR[1]), TARGET_ADDR[0])
        super().__init__(*args, **kwargs)

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
        parser = ProxyHTMLParser(
            callbacks={
                'a': self.fix_link,
                'data': self.wrap_words
            }
        )
        self._html_data = data.splitlines()
        parser.feed(data)
        return '\n'.join(self._html_data)

    def fix_link(self, attrs, lineno, start_pos, end_pos):
        attrs = dict(attrs)
        if 'href' in attrs and self._target_link in attrs['href']:
            attrs['href'] = attrs['href'].replace(self._target_link, self._local_link)
            attrs_string = ' '.join('{}="{}"'.format(k, v) for k, v in attrs.items())
            link = '<a {}>'.format(attrs_string)
            line = self._html_data[lineno - 1]
            self._html_data[lineno - 1] = line[:start_pos] + link + line[end_pos:]

    def wrap_words(self, data, lineno, start_pos):
        pass

    # def wrap_words(self, data):
        # re.sub(b'>([^<>\s]{6})<', 'repl', 'string')
        # return data


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
