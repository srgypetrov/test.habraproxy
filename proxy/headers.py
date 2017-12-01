from collections import UserDict


class Headers(UserDict):

    def __init__(self, headers_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if headers_list:
            self['general'] = headers_list.pop(0).strip()
        for line in headers_list:
            key, value = line.split(':', maxsplit=1)
            self[key] = value.strip()

    def __bytes__(self):
        lines = []
        lines.append(self['general'])
        for key, value in self.items():
            if key != 'general':
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
            header_list.append(received.decode('utf8'))
        return cls(header_list)
