from html.parser import HTMLParser


class ProxyHTMLParser(HTMLParser):

    def __init__(self, callbacks=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_enabled = True
        self.starttag_end_index = 0
        self.callbacks = callbacks or {}

    def get_data_pos(self, data):
        start_lineno, start_pos = self.getpos()
        lines_count = data.count('\n')
        if lines_count:
            end_lineno = start_lineno + lines_count
            end_pos = len(data.splitlines()[-1])
        else:
            end_lineno = start_lineno
            end_pos = start_pos + len(data)
        return start_lineno, start_pos, end_lineno, end_pos

    def get_starttag_pos(self):
        start_lineno, start_pos = self.getpos()
        end_lineno = self.rawdata.count('\n', 0, self.starttag_end_index) + 1
        line_index = self.rawdata.rindex('\n', 0, self.starttag_end_index) + 1
        end_pos = self.starttag_end_index - line_index
        return start_lineno, start_pos, end_lineno, end_pos

    def handle_data(self, data):
        if 'data' in self.callbacks and self.data_enabled and data.strip():
            pos = self.get_data_pos(data)
            self.callbacks['data'](data, *pos)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.data_enabled = True

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.data_enabled = False
        if tag in self.callbacks:
            pos = self.get_starttag_pos()
            self.callbacks[tag](attrs, *pos)

    def parse_starttag(self, i):
        self.starttag_end_index = self.check_for_whole_start_tag(i)
        return super().parse_starttag(i)
