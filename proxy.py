import re
import ssl
import socket
import socketserver
import gzip

HOST, PORT = "localhost", 9999
BUFF = 2048
SITE = 'habrahabr.ru'


class ChunkedResponseError(Exception):
    pass


class ChunkedResponse(object):

    def __init__(self, raw_content):
        self.raw_headers, self.raw_data = raw_content.strip().split(b'\r\n\r\n')
        self.headers = self.unpack_headers()
        if not self.headers.get('Transfer-Encoding') == 'chunked':
            raise ChunkedResponseError('Invalid Transfer-Encoding')
        if not self.headers.get('Content-Encoding') == 'gzip':
            raise ChunkedResponseError('Invalid Content-Encoding')
        self.data, self.chunks_count = self.unpack_data()

    def unpack_headers(self):
        headers = {}
        for line in self.raw_headers.decode('utf8').splitlines():
            if ':' in line:
                k, v = line.split(b':', maxsplit=1)
                headers[k] = v.strip()
        return headers

    def unpack_data(self):
        chunks = self.raw_data.split(b'\r\n')[1::2]
        compressed_data = b''.join(chunks)
        data = gzip.decompress(compressed_data)
        return data.decode('utf8'), len(chunks)

    def get_chunks(self):
        compressed_data = gzip.compress(bytes(self.data, 'utf8'))
        chunk_size = int(len(compressed_data) / self.chunks_count)
        for i in range(0, len(compressed_data), chunk_size):
            chunk_data = compressed_data[i:i + chunk_size]
            chunk_len = format(len(chunk_data), 'x').encode('utf8')
            yield b'%s\r\n%s\r\n' % (chunk_len, chunk_data)
        yield b'0\r\n\r\n'

    def __iter__(self):
        yield self.headers + b'\r\n\r\n'
        for chunk in self.get_chunks():
            yield chunk


class ProxyHandler(socketserver.BaseRequestHandler):

    def handle(self):
        data = self.request.recv(BUFF)
        print(data)
        if data:
            data = data.replace(bytes('Host: {}:{}'.format(HOST, PORT), 'utf8'),
                                bytes('Host: {}'.format(SITE), 'utf8'))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            ss = ssl.wrap_socket(s, ssl_version=ssl.PROTOCOL_TLSv1)
            ss.connect((SITE, 443))
            ss.send(data)
            chunks = self.get_chunks(ss)
            ss.close()
            content = b''.join(chunks)
            if content:
                self.request.sendall(content)

    def get_chunks(self, sock):
        chunks = []
        obtaining = True
        while obtaining:
            received = sock.recv(BUFF)
            chunks.append(received)
            obtaining = self.check_chunk_size(received)
        return chunks

    def check_chunk_size(self, chunk):
        sizes = re.findall(rb'\r\n([0-9A-F]+)\r\n', chunk, re.I)
        return not any(size == b'0' for size in sizes)

    def sdfsdf(self):
        re.sub(b'>([^<>\s]{6})<', 'repl', 'string')


if __name__ == "__main__":
    server = socketserver.TCPServer((HOST, PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
