import re
import ssl
import socket
import socketserver

HOST, PORT = "localhost", 9999
BUFF = 2048
SITE = 'habrahabr.ru'


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
        if any(size == b'0' for size in sizes):
            return False
        return True


if __name__ == "__main__":
    server = socketserver.TCPServer((HOST, PORT), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
