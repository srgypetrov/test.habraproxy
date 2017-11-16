import gzip
import logging
import re
import socket
import socketserver
import ssl

from collections import UserDict, defaultdict
from contextlib import contextmanager
from copy import copy
from html.parser import HTMLParser

LOCAL_ADDR = ('localhost', 9999)
TARGET_ADDR = ('habrahabr.ru', 443)

LOCAL_LINK = 'http://{}:{}'.format(*LOCAL_ADDR)
TARGET_LINK = '{}://{}'.format(
    socket.getservbyport(TARGET_ADDR[1]), TARGET_ADDR[0])


class ProxyHTMLParser(HTMLParser):

    def __init__(self, callbacks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_enabled = True
        self.starttag_end_index = 0
        self.callbacks = callbacks or {}

    def get_data_pos(self, data):
        start_lineno, start_pos = self.getpos()
        lines_count = data.count('\n')
        if lines_count:
            end_lineno = start_lineno + lines_count
            end_pos = len(data.splitlines()[-1])
        else:
            end_lineno = start_lineno
            end_pos = start_pos + len(data)
        return start_lineno, start_pos, end_lineno, end_pos

    def get_starttag_pos(self):
        start_lineno, start_pos = self.getpos()
        end_lineno = self.rawdata.count('\n', 0, self.starttag_end_index) + 1
        line_index = self.rawdata.rindex('\n', 0, self.starttag_end_index) + 1
        end_pos = self.starttag_end_index - line_index
        return start_lineno, start_pos, end_lineno, end_pos

    def handle_data(self, data):
        if 'data' in self.callbacks and self.data_enabled and data.strip():
            pos = self.get_data_pos(data)
            self.callbacks['data'](data, *pos)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.data_enabled = True

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.data_enabled = False
        if tag in self.callbacks:
            pos = self.get_starttag_pos()
            self.callbacks[tag](attrs, *pos)

    def parse_starttag(self, i):
        self.starttag_end_index = self.check_for_whole_start_tag(i)
        return super().parse_starttag(i)


class Headers(UserDict):

    def __init__(self, headers_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for line in headers_list:
            line = line.decode('utf8')
            if ':' in line:
                key, value = line.split(':', maxsplit=1)
                self[key] = value.strip()
            else:
                self['general'] = line.strip()

    def __bytes__(self):
        lines = []
        lines.append(self.pop('general'))
        for key, value in self.items():
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

    @property
    def path(self):
        general = self.headers['general'].split()
        return general[1]


class Response(object):

    def __init__(self, headers, data=None, chunks_count=0):
        self._data = None
        self.headers = headers
        self.packed_data = data
        self.chunks_count = chunks_count
        self.unpack_data()
        self.fix_redirect()

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

    def fix_redirect(self):
        if self.status in (301, 302):
            location = self.headers['Location']
            if TARGET_LINK in location:
                self.headers['Location'] = location.replace(TARGET_LINK,
                                                            LOCAL_LINK)

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
            yield self.get_chunk(slice(0))

    def is_chunked(self):
        chunked = self.headers.get('Transfer-Encoding') == 'chunked'
        return chunked and self.packed_data is not None

    def is_gzipped_html(self):
        gzipped = self.headers.get('Content-Encoding') == 'gzip'
        is_html = self.headers.get(
            'Content-Type') == 'text/html; charset=UTF-8'
        return gzipped and is_html and self.packed_data is not None

    def pack_data(self):
        if self.is_gzipped_html():
            self.packed_data = gzip.compress(self.data.encode('utf8'))

    @property
    def status(self):
        general = self.headers['general'].split()
        return int(general[1])

    def unpack_data(self):
        if self.is_gzipped_html():
            data = gzip.decompress(self.packed_data)
            self._data = data.decode('utf8')


class ProxyHandler(socketserver.StreamRequestHandler):

    blacklist = {
        # disable auto redirect when user is logged in
        '/auth/login/?checklogin=true': '/'
    }

    def __init__(self, *args, **kwargs):
        self._html_data = None
        self._html_offsets = defaultdict(int)
        super().__init__(*args, **kwargs)

    def handle(self):
        headers = Headers.from_rfile(self.rfile)
        if headers:
            request = Request(headers)
            if request.path in self.blacklist:
                return self.handle_disabled_path(request.path)
            logging.debug(request.headers['general'])
            response = request.make_request()
            logging.debug(response.headers['general'])
            if response.is_gzipped_html():
                response.data = self.modify_data(response.data)
            for chunk in response:
                self.wfile.write(chunk)

    def handle_disabled_path(self, path):
        logging.info('Cancelled: %s', path)
        redirect_path = self.blacklist[path]
        if redirect_path is not None:
            logging.info('Redirect to: %s', redirect_path)
            headers = Headers([], general='HTTP/1.1 302 Found',
                              Location=redirect_path)
            self.wfile.write(bytes(headers))
        return

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

    def fix_link(self, attrs, start_lineno, start_pos, end_lineno, end_pos):
        attrs = dict(attrs)
        if 'href' in attrs and TARGET_LINK in attrs['href']:
            attrs['href'] = attrs['href'].replace(TARGET_LINK, LOCAL_LINK)
            attrs_string = ' '.join('{}="{}"'.format(k, v)
                                    for k, v in attrs.items())
            link = '<a {}>'.format(attrs_string)
            if start_lineno != end_lineno:
                lines = [link] + [''] * (end_lineno - start_lineno)
                self.replace_lines(lines, start_lineno,
                                   start_pos, end_lineno, end_pos)
            else:
                self.replace_line(link, start_lineno, start_pos, end_pos)

    def wrap_words(self, data, start_lineno, start_pos, end_lineno, end_pos):
        fixed_data, count = re.subn(r'(\b\w{6}\b)', r'\1' + '\u2122', data)
        if count:
            if start_lineno != end_lineno:
                lines = fixed_data.splitlines()
                self.replace_lines(lines, start_lineno,
                                   start_pos, end_lineno, end_pos)
            else:
                self.replace_line(fixed_data, start_lineno, start_pos, end_pos)

    def replace_lines(self, lines, start_lineno, start_pos,
                      end_lineno, end_pos):
        for i, item in enumerate(lines):
            lineno = start_lineno + i
            if lineno == start_lineno:
                self.replace_line(item, lineno, start_pos=start_pos)
            elif lineno == end_lineno:
                self.replace_line(item, lineno, end_pos=end_pos)
            else:
                self.replace_line(item, lineno)

    def replace_line(self, line, lineno, start_pos=0, end_pos=0):
        index = lineno - 1
        start_pos, end_pos = self.calculate_offset(
            len(line), index, start_pos, end_pos)
        begin = self._html_data[index][:start_pos]
        end = self._html_data[index][end_pos:]
        self._html_data[index] = begin + line + end

    def calculate_offset(self, line_length, index, start_pos, end_pos):
        offset = self._html_offsets.get(index, 0)
        start_pos += offset
        if end_pos:
            end_pos += offset
            new_offset = line_length - (end_pos - start_pos)
            if new_offset:
                self._html_offsets[index] += new_offset
        else:
            end_pos = len(self._html_data[index])
        return start_pos, end_pos


def main():
    server = socketserver.TCPServer(LOCAL_ADDR, ProxyHandler)
    logging.basicConfig(
        format='%(message)s | %(asctime)s | %(levelname)s',
        level=logging.DEBUG,
        handlers=[logging.StreamHandler()]
    )
    print('Starting proxy server at {}/'.format(LOCAL_LINK),
          'Quit the server with CONTROL-C.', sep='\n', end='\n\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
