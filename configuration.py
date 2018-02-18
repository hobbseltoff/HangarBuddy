""" Module to abstract and hide configuration. """

# encoding: UTF-8

import json
from ConfigParser import SafeConfigParser

# read in configuration settings
# $TODO - Add a name to each phone number so we can track who it is.
# $TODO - For response that contain a phone number, use the friendly name instead
# $TODO - More finely tune control of the numbers the response is sent to.
# $TODO - Move config over fully to JSON
# $TODO - Handle "no phone numbers in config" scenario for setup/new device


def get_config_file_location():
    """
    Get the location of the configuration file.

    >>> get_config_file_location()
    './HangarBuddy.config'
    """

    return './HangarBuddy.config'


class ConfigurationItem(object):
    """
    Object that handles a configuraiton item.
    """

    def get(self):
        """
        Returns the current value.
        """
        return self.__value__

    def get_int(self):
        """
        Returns the value as an int.
        """
        try:
            if self.__value__ is not None:
                return int(self.__value__)
        except:
            pass

        return 0

    def get_float(self):
        """
        Returns the value as a float.
        """
        try:
            if self.__value__ is not None:
                return float(self.__value__)
        except:
            pass

        return 0.0

    def get_array(self):
        """
        Returns the value as an array delimited
        by commas.
        """
        try:
            if self.__value__ is not None:
                return self.__value__.split(',')
        except:
            pass

        return []

    def get_bool(self):
        """
        Returns the value as a boolean.
        """
        try:
            if self.__value__ is not None:
                return bool(self.__value__)
        except:
            pass

        return 0.0

    def set(self, new_value):
        """
        Sets the value.
        """
        self.__value__ = new_value

        str_value = str(new_value)

        # Make sure phone numbers get converted properly
        if isinstance(new_value, list):
            str_value = ""
            for item in new_value:
                str_value += item + ","
            
            str_value = str_value[:len(str_value) - 1]

        self.__config__.set(self.section_name,
                            self.key_name, str_value)

    def __init__(self, config_parser, section_name, key_name, default_value=None):
        self.__config__ = config_parser
        self.section_name = section_name
        self.key_name = key_name
        self.__value__ = default_value

        if config_parser is not None:
            try:
                self.__value__ = config_parser.get(section_name, key_name)
            except:
                self.__value__ = default_value


class Configuration(object):
    """
    Object to handle configuration of the HangarBuddy.
    """

    def write_with_location(self, file_location):
        """
        Writes the config file to the given locaiton.
        """

        with open(file_location, 'w') as configfile:
            self.__config_parser__.write(configfile)

    def write(self):
        self.write_with_location(get_config_file_location())

    def get_json_from_text(self, text):
        """
        Takes raw text and imports it into JSON.
        """

        return json.loads(text)
    
    def get_json_from_config(self):
        """
        Returns the current config as JSON text.

        REMARK: Returns everything back as a string...
                That is probably safer, but not nearly
                as convient as I want
        """
        config_dictionary = {s:dict(self.__config_parser__.items(s)) for s in self.__config_parser__.sections()}

        return json.dumps(config_dictionary)

    def set_from_json(self, json_config):
        """
        Takes a JSON package and sets the config using the JSON
        """

        if json_config is None:
            return

        for config_item in self.configuration_items:
            try:
                if config_item.section_name in json_config and config_item.key_name in json_config[config_item.section_name]:
                    config_item.set(
                        json_config[config_item.section_name.upper()][config_item.key_name.upper()])
            except:
                pass

    def get_log_directory(self):
        """ returns the location of the logfile to use. """

        return self.logfile_directory.get()

    def __init__(self):
        self.__config_parser__ = SafeConfigParser()
        # Keep the capitalization of the
        # key names in the .INI
        self.__config_parser__.optionxform = str
        self.__config_parser__.read(get_config_file_location())

        self.logfile_directory = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'LOGFILE_DIRECTORY',
            './'
        )

        # Sets the port for the serial connection of the Fona on USB.
        # NOTE: Requires a software restart.
        # NOTE: Should be in the form of /dev/ttyUSB0
        self.fona_serial_port = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'SERIAL_PORT',
            '/dev/ttyUSB0')

        # Sets the baud rate of the Fona.
        # NOTE: Requires a software restart.
        self.fona_baud_rate = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'BAUDRATE',
            '9600'
        )

        # Sets the pin that the power status pin is on.
        # (BOARD numbering)
        self.fona_power_status_pin = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'POWER_STATUS_PIN',
            '16'
        )

        # Sets the pin the ring indicator is on.
        # (BOARD numbering)
        self.fona_ring_indicator_pin = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'RING_INDICATOR_PIN',
            '18'
        )

        # Sets the pin the heater control/relay is on.
        # (BOARD numbering)
        self.relay_control_pin = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'HEATER_PIN',
            '22'
        )

        # Sets the value of the light sensor that below
        # which is considered dark.
        self.hangar_dark_threshold = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'HANGAR_DARK',
            '20'
        )

        # Sets the value of the light sensor that below
        # which is considered dim.
        self.hangar_dim_threshold = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'HANGAR_DIM',
            '60'
        )

        # Sets the value of the light sensor that above
        # which is considered the lights are on.
        self.hangar_lit_threshold = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'HANGAR_LIT',
            '90'
        )

        # Sets phone numbers that are allowed to issue commands.
        # NOTE: Expects an array of phone numbers.
        self.allowed_phone_numbers = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'ALLOWED_PHONE_NUMBERS',
            ''
        )

        # Sets the maximum number of minutes for the unit to run
        # for a single command.
        self.max_heater_timer = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'MAX_HEATER_TIME',
            '90'
        )

        # Sets the numnber of minutes that if a message is older
        # than, then it gets ignored.
        self.maximum_message_age = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'OLDEST_MESSAGE_TO_PROCESS',
            '30'
        )

        # Sets offetset from UTC
        # (Number of hours)
        self.utc_offset = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'UTC_OFFSET',
            '8'
        )

        # Controls if the system is in test mode
        self.test_mode = ConfigurationItem(
            self.__config_parser__,
            'SETTINGS', 'TEST_MODE',
            'False'
        )

        self.configuration_items = [self.allowed_phone_numbers, self.utc_offset, self.maximum_message_age,
                                self.max_heater_timer, self.logfile_directory,
                                self.fona_serial_port, self.fona_baud_rate,
                                self.fona_power_status_pin, self.fona_ring_indicator_pin,
                                self.relay_control_pin, self.hangar_dark_threshold,
                                self.hangar_dim_threshold, self.hangar_lit_threshold,
                                self.test_mode]

        self.log_filename = self.get_log_directory() + "hangar_buddy.log"

    def load_config_from_json_file(self, input_filepath, output_settings_file):
        with open(input_filepath) as json_config_file:
            json_config_text = json_config_file.read()
            json = self.get_json_from_text(json_config_text)
            self.set_from_json(json)

            self.write_with_location(output_settings_file)


##################
### UNIT TESTS ###
##################

def test_configuration():
    """ Test that the configuration is valid. """
    config = Configuration()

    assert config.allowed_phone_numbers.get() is not None
    assert config.allowed_phone_numbers.get_array().count > 0
    assert config.fona_baud_rate.get() == '9600'
    assert config.fona_serial_port.get() is not None
    assert config.relay_control_pin.get() is not None
    assert config.relay_control_pin.get_int() >= 1
    assert config.relay_control_pin.get_int() < 32
    assert config.log_filename is not None
    assert config.max_heater_timer.get_int() >= 60


if __name__ == '__main__':
    import doctest

    doctest.testmod()

    # Exercise the INI -> JSON -> INI -> JSON code
    config_from_json = Configuration()
    config_from_json.load_config_from_json_file('test/config.json', 'test/from_json.config')
    config_from_json.load_config_from_json_file('test/config_updated.json', 'test/updated_from_json.config')

    with open('test/update_config_output.json', 'w') as configfile:
        configfile.write(config_from_json.get_json_from_config())

