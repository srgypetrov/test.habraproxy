import re
from collections import defaultdict

from .parser import ProxyHTMLParser
from .settings import settings


class Modifier(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._html_data = None
        self._html_offsets = defaultdict(int)

    def calculate_offset(self, line_length, index, start_pos, end_pos):
        offset = self._html_offsets.get(index, 0)
        start_pos += offset
        if end_pos:
            end_pos += offset
            new_offset = line_length - (end_pos - start_pos)
            if new_offset:
                self._html_offsets[index] += new_offset
        else:
            end_pos = len(self._html_data[index])
        return start_pos, end_pos

    def fix_link(self, attrs, start_lineno, start_pos, end_lineno, end_pos):
        attrs = dict(attrs)
        if 'href' in attrs and settings.target_link in attrs['href']:
            attrs['href'] = attrs['href'].replace(settings.target_link,
                                                  settings.local_link)
            attrs_string = ' '.join('{}="{}"'.format(k, v)
                                    for k, v in attrs.items())
            link = '<a {}>'.format(attrs_string)
            if start_lineno != end_lineno:
                lines = [link] + [''] * (end_lineno - start_lineno)
                self.replace_lines(lines, start_lineno,
                                   start_pos, end_lineno, end_pos)
            else:
                self.replace_line(link, start_lineno, start_pos, end_pos)

    def modify_data(self, data):
        parser = ProxyHTMLParser(
            callbacks={
                'a': self.fix_link,
                'data': self.wrap_words
            }
        )
        self._html_data = data.splitlines()
        parser.feed(data)
        return '\n'.join(self._html_data)

    def replace_line(self, line, lineno, start_pos=0, end_pos=0):
        index = lineno - 1
        start_pos, end_pos = self.calculate_offset(
            len(line), index, start_pos, end_pos)
        begin = self._html_data[index][:start_pos]
        end = self._html_data[index][end_pos:]
        self._html_data[index] = begin + line + end

    def replace_lines(self, lines, start_lineno, start_pos,
                      end_lineno, end_pos):
        for i, item in enumerate(lines):
            lineno = start_lineno + i
            if lineno == start_lineno:
                self.replace_line(item, lineno, start_pos=start_pos)
            elif lineno == end_lineno:
                self.replace_line(item, lineno, end_pos=end_pos)
            else:
                self.replace_line(item, lineno)

    def wrap_words(self, data, start_lineno, start_pos, end_lineno, end_pos):
        fixed_data, count = re.subn(r'(\b\w{6}\b)', r'\1' + '\u2122', data)
        if count:
            if start_lineno != end_lineno:
                lines = fixed_data.splitlines()
                self.replace_lines(lines, start_lineno,
                                   start_pos, end_lineno, end_pos)
            else:
                self.replace_line(fixed_data, start_lineno, start_pos, end_pos)
