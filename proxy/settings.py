import socket


class Settings(object):

    defaults = {
        'target_host': 'habrahabr.ru',
        'local_host': 'localhost',
        'target_port': 443,
        'local_port': 9090,
        'blacklist': {
            # disable auto redirect when user is logged in
            '/auth/login/?checklogin=true': '/'
        }
    }

    def __init__(self):
        self._data = dict(self.defaults)

    def __getattr__(self, name):
        return self._data[name]

    def update(self, **kwargs):
        self._data.update(kwargs)

    @property
    def local_addr(self):
        return (self.local_host, self.local_port)

    @property
    def local_link(self):
        return 'http://{}:{}'.format(*self.local_addr)

    @property
    def target_addr(self):
        return (self.target_host, self.target_port)

    @property
    def target_link(self):
        return '{}://{}'.format(
            socket.getservbyport(self.target_addr[1]), self.target_addr[0]
        )

    @property
    def is_secure(self):
        return self.target_port == 443


settings = Settings()
