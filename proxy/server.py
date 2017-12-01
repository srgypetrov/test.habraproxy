import logging
import socketserver

from .handler import ProxyHandler
from .settings import settings


def run_server(local_port=None, target_host=None, target_port=None):
    if target_host is not None:
        settings.update(target_host=target_host)
    if local_port is not None:
        settings.update(local_port=local_port)
    if target_port is not None:
        settings.update(target_port=target_port)
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
