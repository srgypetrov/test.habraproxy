import logging
import socketserver

from .headers import Headers
from .modifier import Modifier
from .request import Request


class ProxyHandler(socketserver.StreamRequestHandler):

    blacklist = {
        # disable auto redirect when user is logged in
        '/auth/login/?checklogin=true': '/'
    }
    redirect_header = 'HTTP/1.1 302 Found'

    def handle(self):
        headers = Headers.from_rfile(self.rfile)
        if headers:
            request = Request(headers)
            if request.path in self.blacklist:
                return self.handle_disabled_path(request.path)
            logging.debug(request.headers['general'])
            response = request.make_request()
            logging.debug(response.headers['general'])
            if response.is_gzipped_html():
                modifier = Modifier()
                response.data = modifier.modify_data(response.data)
            for chunk in response:
                self.wfile.write(chunk)

    def handle_disabled_path(self, path):
        logging.info('Cancelled: %s', path)
        redirect_path = self.blacklist[path]
        if redirect_path is not None:
            logging.info('Redirect to: %s', redirect_path)
            headers = Headers([], general=self.redirect_header,
                              Location=redirect_path)
            self.wfile.write(bytes(headers))
