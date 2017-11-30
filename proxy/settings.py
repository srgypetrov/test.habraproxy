import socket


class Settings(object):

    local_addr = ('localhost', 9090)
    target_addr = ('habrahabr.ru', 443)

    def __init__(self, *args, **kwargs):
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

    def change_local_port(self, port):
        self.local_addr = (self.local_addr[0], port)


settings = Settings()
