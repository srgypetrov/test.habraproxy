import argparse
import socket


def parse_args():
    parser = argparse.ArgumentParser(description='Habraproxy.')
    parser.add_argument('--port', type=int, nargs='?', default=9090,
                        const=9090, help='local port for proxy server')
    return parser.parse_args()


class Settings(object):

    def __init__(self, port, *args, **kwargs):
        self.local_addr = ('localhost', port)
        self.target_addr = ('habrahabr.ru', 443)
        self.data = dict(**kwargs)

    def __getattr__(self, name):
        return self.data[name]

    @property
    def local_link(self):
        return 'http://{}:{}'.format(*self.local_addr)

    @property
    def target_link(self):
        return '{}://{}'.format(
            socket.getservbyport(self.target_addr[1]), self.target_addr[0]
        )


_args = parse_args()
settings = Settings(_args.port)
