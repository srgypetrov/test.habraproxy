from collections import UserDict


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
