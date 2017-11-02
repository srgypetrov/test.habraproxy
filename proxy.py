import gzip
import logging
import re
import socket
import socketserver
import ssl

from contextlib import contextmanager


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
        content_encoding = self.headers.get('Content-Encoding')
        content_type = self.headers.get('Content-Type')
        if transfer_encoding != 'chunked':
            raise ChunkedResponseError('Invalid Transfer-Encoding', transfer_encoding)
        if content_encoding != 'gzip':
            raise ChunkedResponseError('Invalid Content-Encoding', content_encoding)
        if content_type != 'text/html; charset=UTF-8':
            raise ChunkedResponseError('Invalid Content-Type', content_type)

    def get_chunks(self):
        compressed_data = gzip.compress(bytes(self.data, 'utf8'))
        chunk_size = int(len(compressed_data) / self.chunks_count)
        for i in range(0, len(compressed_data), chunk_size):
            chunk_data = compressed_data[i:i + chunk_size]
            chunk_len = format(len(chunk_data), 'x').encode('utf8')
            yield b'%s\r\n%s\r\n' % (chunk_len, chunk_data)
        yield b'0\r\n\r\n'

    def unpack_data(self):
        patterns = [rb'\r\n[0-9A-F]+$', rb'\r\n[0-9A-F]+\r\n', rb'^[0-9A-F]+\r\n']
        compressed_data, count = re.subn(rb'|'.join(patterns), b'', self.raw_data, flags=re.I)
        data = gzip.decompress(compressed_data)
        return data.decode('utf8'), count

    def unpack_headers(self):
        headers = {}
        for line in self.raw_headers.decode('utf8').splitlines():
            if ':' in line:
                k, v = line.split(':', maxsplit=1)
                headers[k] = v.strip()
            else:
                headers[line] = None
        return headers


class ProxyHandler(socketserver.StreamRequestHandler):

    target_host = 'habrahabr.ru'
    local_host = '{}:{}'.format(HOST, PORT)
    bufsize = 2048

    def check_for_end(self, chunk):
        if b'\r\n0\r\n' in chunk:
            return False
        if chunk.endswith(b'\r\n\r\n'):
            if b'Content-Length' not in chunk and b'Transfer-Encoding' not in chunk:
                return False
        return True

    def get_content(self, headers):
        chunks = []
        with self.ssl_socket() as sock:
            sock.send(headers)
            obtaining = True
            while obtaining:
                received = sock.recv(self.bufsize)
                chunks.append(received)
                obtaining = self.check_for_end(received)
        return b''.join(chunks)

    def get_headers(self):
        headers = []
        while b'\r\n' not in headers:
            received = self.rfile.readline()
            if not received:
                break
            if received == b'Host: %s\r\n' % self.local_host.encode('utf8'):
                received = b'Host: %s\r\n' % self.target_host.encode('utf8')
            headers.append(received)
        return b''.join(headers)

    def get_response(self, content):
        logging.debug(content.splitlines()[0].decode('utf8'))
        try:
            response = ChunkedResponse(content)
        except ChunkedResponseError:
            response = content
        return response

    def handle(self):
        headers = self.get_headers()
        if headers:
            logging.debug(headers.splitlines()[0].decode('utf8'))
            content = self.get_content(headers)
            response = self.get_response(content)
            if isinstance(response, ChunkedResponse):
                for chunk in response:
                    self.wfile.write(chunk)
            else:
                self.wfile.write(response)

    @contextmanager
    def ssl_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ssl_sock = ssl.wrap_socket(sock, ssl_version=ssl.PROTOCOL_TLSv1)
        ssl_sock.connect((self.target_host, 443))
        yield ssl_sock
        ssl_sock.close()

    # def sdfsdf(self):
    #     re.sub(b'>([^<>\s]{6})<', 'repl', 'string')


if __name__ == "__main__":
    logging.basicConfig(
        format='%(message)s | %(asctime)s | %(levelname)s',
        level=logging.DEBUG,
        handlers=[logging.StreamHandler()]
    )
    server = socketserver.TCPServer((HOST, PORT), ProxyHandler)
    print('Starting proxy server at http://{}:{}/'.format(HOST, PORT),
          'Quit the server with CONTROL-C.', sep='\n', end='\n\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
