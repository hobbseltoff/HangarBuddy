import sys
import datetime
import socket
import json
import shutil
import urllib
import os
import re
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import lib.utilities as utilities
from configuration import Configuration 

CONFIGURATION = None

# EXAMPLES
# Invoke-WebRequest -Uri "http://localhost:8080/settings" -Method GET -ContentType "application/json"
# Invoke-WebRequest -Uri "http://localhost:8080/settings" -Method PUT -ContentType "application/json" -Body '{"SETTINGS": {"BAUDRATE": 1234}}'

def get_settings(handler):
    if CONFIGURATION is not None:
        return CONFIGURATION.get_json_from_config()
    else:
        return None

def set_settings(handler):
    if CONFIGURATION is not None:
        payload = handler.get_payload()
        CONFIGURATION.set_from_json(payload)
        return CONFIGURATION.get_json_from_config()
    else:
        return None

class RestfulHost(BaseHTTPRequestHandler):
    """
    Handles the HTTP response for status.
    """

    HERE = os.path.dirname(os.path.realpath(__file__))
    ROUTES = {
        r'^/settings': {'GET': get_settings, 'PUT': set_settings, 'media_type': 'application/json'}}
    
    def do_HEAD(self):
        self.handle_method('HEAD')
    
    def do_GET(self):
        self.handle_method('GET')

    def do_POST(self):
        self.handle_method('POST')

    def do_PUT(self):
        self.handle_method('PUT')

    def do_DELETE(self):
        self.handle_method('DELETE')
    
    def get_payload(self):
        payload_len = int(self.headers.getheader('content-length', 0))
        payload = self.rfile.read(payload_len)
        payload = json.loads(payload)
        return payload
        
    def handle_method(self, method):
        route = self.get_route()
        if route is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write('Route not found\n')
        else:
            if method == 'HEAD':
                self.send_response(200)
                if 'media_type' in route:
                    self.send_header('Content-type', route['media_type'])
                self.end_headers()
            else:
                if 'file' in route:
                    if method == 'GET':
                        try:
                            f = open(os.path.join(RestfulHost.HERE, route['file']))
                            try:
                                self.send_response(200)
                                if 'media_type' in route:
                                    self.send_header('Content-type', route['media_type'])
                                self.end_headers()
                                shutil.copyfileobj(f, self.wfile)
                            finally:
                                f.close()
                        except:
                            self.send_response(404)
                            self.end_headers()
                            self.wfile.write('File not found\n')
                    else:
                        self.send_response(405)
                        self.end_headers()
                        self.wfile.write('Only GET is supported\n')
                else:
                    if method in route:
                        content = route[method](self)
                        if content is not None:
                            self.send_response(200)
                            if 'media_type' in route:
                                self.send_header('Content-type', route['media_type'])
                            self.end_headers()
                            if method != 'DELETE':
                                self.wfile.write(json.dumps(content))
                        else:
                            self.send_response(404)
                            self.end_headers()
                            self.wfile.write('Not found\n')
                    else:
                        self.send_response(405)
                        self.end_headers()
                        self.wfile.write(method + ' is not supported\n')
                    
    
    def get_route(self):
        for path, route in RestfulHost.ROUTES.iteritems():
            if re.match(path, self.path):
                return route
        return None


if __name__ == '__main__':
    CONFIGURATION = Configuration()
    CONFIGURATION.load_config_from_json_file('test/config.json', 'test/from_json.config')

    # port = 80
    # local_ip = [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(
    #    ('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]

    # if local_debug.is_debug():
    local_ip = ''
    port = 8080

    print str(local_ip) + "localhost:" + str(port)

    server_address = (local_ip, port)
    httpd = HTTPServer(server_address, RestfulHost)
    httpd.serve_forever()