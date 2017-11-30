import logging
import socketserver

from .handler import ProxyHandler
from .settings import settings


def run_server():
    server = socketserver.TCPServer(settings.local_addr, ProxyHandler)
    logging.basicConfig(
        format='%(message)s | %(asctime)s | %(levelname)s',
        level=logging.DEBUG,
        handlers=[logging.StreamHandler()]
    )
    print('Starting proxy server at {}/'.format(settings.local_link),
          'Quit the server with CONTROL-C.', sep='\n', end='\n\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
