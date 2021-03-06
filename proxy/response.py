import gzip
import socket
from urllib.parse import urlparse

from .settings import settings


class Response(object):

    html_content_type = 'text/html; charset=utf-8'

    def __init__(self, headers, packed_data=None, chunks_count=0):
        self._data = None
        self.headers = headers
        self.packed_data = packed_data
        self.chunks_count = chunks_count
        self.unpack_data()
        self.handle_redirect()

    def __iter__(self):
        yield bytes(self.headers)
        if self.is_chunked():
            for chunk in self.get_chunks():
                yield chunk
        elif self.packed_data is not None:
            yield self.packed_data

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self.pack_data()

    def handle_redirect(self):
        if self.status in (301, 302):
            location = self.headers['Location']
            url = urlparse(location)
            settings.update(target_port=socket.getservbyname(url.scheme),
                            target_host=url.hostname)
            self.headers['Location'] = location.replace(
                settings.target_link, settings.local_link
            )

    def get_chunk(self, part_slice):
        chunk_data = self.packed_data[part_slice]
        chunk_len = format(len(chunk_data), 'x').encode('utf8')
        return b'%s\r\n%s\r\n' % (chunk_len, chunk_data)

    def get_chunks(self):
        if self.is_chunked():
            chunk_size = int(len(self.packed_data) / self.chunks_count)
            for i in range(0, len(self.packed_data), chunk_size):
                if len(self.packed_data[i:]) < chunk_size * 1.5:
                    yield self.get_chunk(slice(i, None))
                    break
                yield self.get_chunk(slice(i, i + chunk_size))
            yield self.get_chunk(slice(0))

    def is_chunked(self):
        transfer_encoding = self.headers.get('Transfer-Encoding', '')
        chunked = transfer_encoding.lower() == 'chunked'
        return chunked and self.packed_data is not None

    def is_gzipped_html(self):
        content_encoding = self.headers.get('Content-Encoding', '')
        content_type = self.headers.get('Content-Type', '')
        gzipped = content_encoding.lower() == 'gzip'
        is_html = content_type.lower() == self.html_content_type
        return gzipped and is_html and self.packed_data is not None

    def pack_data(self):
        if self.is_gzipped_html():
            self.packed_data = gzip.compress(self.data.encode('utf8'))

    @property
    def status(self):
        general = self.headers['general'].split()
        return int(general[1])

    def unpack_data(self):
        if self.is_gzipped_html():
            data = gzip.decompress(self.packed_data)
            self._data = data.decode('utf8')
