""" Contains the response generated by a command request. """

HEATER_OFF = "OFF"
HEATER_ON = "ON"
PI_WARMER_OFF = "SHUTDOWN"
PI_WARMER_RESTART = "RESTART"
STATUS = "STATUS"
HELP = "HELP"
ERROR = "ERROR"
NOOP = "NOOP"

VALID_COMMANDS = {HEATER_OFF, HEATER_ON, PI_WARMER_OFF, PI_WARMER_RESTART, STATUS, HELP}


class CommandResponse(object):
    """ Object to return a command response. """

    def get_command(self):
        """ Returns the command. """
        return self.__command__

    def get_message(self):
        """ Returns the message """
        if self.__message__ is None:
            return ""

        return self.__message__

    def __init__(self, command, message):
        if command in VALID_COMMANDS:
            self.__command__ = command
        else:
            self.__command__ = HELP

        self.__message__ = message

##################
### UNIT TESTS ###
##################


def test_invalid_command():
    """ Test invalid commands into the response. """
    command_response = CommandResponse("INVALID", "INVALID")
    assert command_response.get_command() == HELP
    assert command_response.get_message() == "INVALID"


def test_valid_commands():
    """ Test that valid commands come back as they should. """
    for command in VALID_COMMANDS:
        message = "2061234567 " + command + " message."
        print "Testing " + command + " " + message
        command_response = CommandResponse(command, message)
        assert command_response.get_command() == command
        assert command_response.get_message() == message