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
import lib.local_debug as local_debug
import text

CONFIGURATION = None
COMMAND_PROCESSOR = None

# Based on https://gist.github.com/tliron/8e9757180506f25e46d9

# EXAMPLES
# Invoke-WebRequest -Uri "http://localhost:8080/settings" -Method GET -ContentType "application/json"
# Invoke-WebRequest -Uri "http://localhost:8080/settings" -Method PUT -ContentType "application/json" -Body '{"SETTINGS": {"BAUDRATE": 1234}}'

ERROR_JSON = '{success: false}'


def get_settings(handler):
    """
    Handles a get-the-settings request.
    """
    if CONFIGURATION is not None:
        return CONFIGURATION.get_json_from_config()
    else:
        return ERROR_JSON


def set_settings(handler):
    """
    Handles a set-the-settings request.
    """
    # $TODO - Actually write the file.
    if CONFIGURATION is not None:
        payload = handler.get_payload()
        CONFIGURATION.set_from_json(payload)
        return CONFIGURATION.get_json_from_config()
    else:
        return ERROR_JSON

def get_json_success_response(text):
    """
    Returns a generic JSON response of success with
    text included in the payload.
    """

    return '{success: true, response:"' + text + '"}'

def start_shutdown(handler):
    """
    Starts the shutdown process.
    """
    if COMMAND_PROCESSOR is not None:
        response = COMMAND_PROCESSOR.process_local_message(
            text.SHUTDOWN_COMMAND)
        return get_json_success_response(response.get_message())
    else:
        return ERROR_JSON

def start_restart(handler):
    """
    Starts the restart process.
    """
    if COMMAND_PROCESSOR is not None:
        response = COMMAND_PROCESSOR.process_local_message(
            text.RESTART_COMMAND)
        return get_json_success_response(response.get_message())
    else:
        return ERROR_JSON

def get_status(handler):
    """
    Handle returning the full status.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_full_status())
    else:
        return ERROR_JSON

def get_help(handler):
    """
    Handle getting the help status.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_help_status())
    else:
        return ERROR_JSON

def get_heater_status(handler):
    """
    Handle getting the heater's status.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_heater_status())
    else:
        return ERROR_JSON

def get_gas_status(handler):
    """
    Returns the status of gas and the gas sensor.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_gas_sensor_status())
    else:
        return ERROR_JSON

def get_cell_status(handler):
    """
    Gets the status of the Cell/Fona
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_cell_status())
    else:
        return ERROR_JSON

def get_light_status(handler):
    """
    Get the current light status.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_light_status())
    else:
        return ERROR_JSON

def get_temperature_status(handler):
    """
    Gets the temperature & sensor status.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_temperature_status())
    else:
        return ERROR_JSON

def get_uptime_status(handler):
    """
    Handles getting the uptime.
    """
    if COMMAND_PROCESSOR is not None:
        return get_json_success_response(COMMAND_PROCESSOR.get_uptime_status())
    else:
        return ERROR_JSON

def queue_start_heater(handler):
    """
    Handles a request to start the heater.
    """
    if COMMAND_PROCESSOR is not None:
        response = COMMAND_PROCESSOR.process_local_message(
            text.HEATER_ON_COMMAND)
        return get_json_success_response(response.get_message())
    else:
        return ERROR_JSON

def queue_stop_heater(handler):
    """
    Handles a request to stop the heater.
    """
    if COMMAND_PROCESSOR is not None:
        response = COMMAND_PROCESSOR.process_local_message(
            text.HEATER_OFF_COMMAND)
        return get_json_success_response(response.get_message())
    else:
        return ERROR_JSON

def queue_test_message(handler):
    """
    Handles a request to send a test message.
    The key "phone" must be set AND the phone
    number must be in the white list for
    safe numbers.
    """

    payload = handler.get_payload()
    if "phone" not in payload:
        return ERROR_JSON
    
    phone_number = payload["phone"]
    
    # TODO: Make this take a phone number as a JSON parameter...
    if COMMAND_PROCESSOR is not None:
        response = COMMAND_PROCESSOR.process_message(text.HELP_COMMAND, phone_number)
        return get_json_success_response(response.get_message())
    else:
        return ERROR_JSON


def get_history(handler):
    """
    Reserved to return a message history.
    """
    # $TODO - Return a message history
    if COMMAND_PROCESSOR is not None:
        return None
    else:
        return ERROR_JSON

class RestfulHost(BaseHTTPRequestHandler):
    """
    Handles the HTTP response for status.
    """

    HERE = os.path.dirname(os.path.realpath(__file__))
    ROUTES = {
        r'^/settings': {'GET': get_settings, 'PUT': set_settings, 'media_type': 'application/json'},
        r'^/system/shutdown': {'PUT': start_shutdown, 'media_type': 'application/json'},
        r'^/system/restart': {'PUT': start_restart, 'media_type': 'application/json'},
        r'^/status/full': {'GET': get_status, 'media_type': 'application/json'},
        r'^/status/help': {'GET': get_help, 'media_type': 'application/json'},
        r'^/status/heater': {'GET': get_heater_status, 'media_type': 'application/json'},
        r'^/status/gas': {'GET': get_gas_status, 'media_type': 'application/json'},
        r'^/status/cell': {'GET': get_cell_status, 'media_type': 'application/json'},
        r'^/status/lights': {'GET': get_light_status, 'media_type': 'application/json'},
        r'^/status/temp': {'GET': get_temperature_status, 'media_type': 'application/json'},
        r'^/status/uptime': {'GET': get_uptime_status, 'media_type': 'application/json'},
        r'^/heater/on': {'PUT': queue_start_heater, 'media_type': 'application/json'},
        r'^/heater/off': {'PUT': queue_stop_heater, 'media_type': 'application/json'},
        r'^/test': {'PUT': queue_test_message, 'media_type': 'application/json'},
        r'^/history': {'PUT': get_history, 'media_type': 'application/json'}
    }

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
    
    def __handle_invalid_route__(self):
        """
        Handles the response to a bad route.
        """
        self.send_response(404)
        self.end_headers()
        self.wfile.write('Route not found\n')
    
    def __handle_file_request__(self, route, method):
        if method == 'GET':
            try:
                f = open(os.path.join(
                    RestfulHost.HERE, route['file']))
                try:
                    self.send_response(200)
                    if 'media_type' in route:
                        self.send_header(
                            'Content-type', route['media_type'])
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
    
    def __finish_get_put_delete_request__(self, route, method):
        if method in route:
            content = route[method](self)
            if content is not None:
                self.send_response(200)
                if 'media_type' in route:
                    self.send_header(
                        'Content-type', route['media_type'])
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
    
    def __handle_request__(self, route, method):
        if method == 'HEAD':
            self.send_response(200)
            if 'media_type' in route:
                self.send_header('Content-type', route['media_type'])
            self.end_headers()
        else:
            if 'file' in route:
                self.__handle_file_request__(route, method)
            else:
                self.__finish_get_put_delete_request__(route, method)


    def handle_method(self, method):
        route = self.get_route()
        if route is None:
            self.__handle_invalid_route__()
        else:
            self.__handle_request__(route, method)
            
    def get_route(self):
        for path, route in RestfulHost.ROUTES.iteritems():
            if re.match(path, self.path):
                return route
        return None


class HangarBuddyServer(object):

    def get_server_ip(self):
        local_ip = [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(
            ('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]

        if local_debug.is_debug():
            local_ip = ''

        return local_ip

    def get_server_port(self):
        port = 80

        if local_debug.is_debug():
            port = 8080

        return port

    def run(self):
        # print str(self.__local_ip__) + "localhost:" + str(self.__port__)

        self.__httpd__.serve_forever()

    def __init__(self):
        self.__port__ = self.get_server_port()
        self.__local_ip__ = self.get_server_ip()
        server_address = (self.__local_ip__, self.__port__)
        self.__httpd__ = HTTPServer(server_address, RestfulHost)


if __name__ == '__main__':
    CONFIGURATION = Configuration()
    CONFIGURATION.load_config_from_json_file(
        'test/config.json', 'test/from_json.config')

    host = HangarBuddyServer()
    host.run()
