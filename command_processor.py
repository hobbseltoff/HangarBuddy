"""
Contains the response generated by a command request.
"""

# TODO - Make commands and help response customizable for Localization
# TODO - Add documentation on all of "pip installs" required


import sys
import time
import Queue
from multiprocessing import Queue as MPQueue
import serial  # Requires "pyserial"
import text
from fona_manager import FonaManager
from Sensors import Sensors
from relay_controller import RelayManager
from lib.recurring_task import RecurringTask
import lib.utilities as utilities
import lib.local_debug as local_debug
from lib.logger import Logger
from lib.sf_1602_lcd import LcdDisplay

# Build a list of the valid commanhds so
# the CommandProcessor can know what to
# look for and CommandResponse can
# reject invalid commands.
VALID_COMMANDS = {text.HEATER_OFF_COMMAND,
                  text.HEATER_ON_COMMAND,
                  text.SHUTDOWN_COMMAND,
                  text.RESTART_COMMAND,
                  text.QUIT_COMMAND,
                  text.FULL_STATUS_COMMAND,
                  text.HELP_COMMAND,
                  text.LIGHTS_COMMAND,
                  text.CELL_STATUS_COMMAND,
                  text.TEMPERATURE_COMMAND,
                  text.UPTIME_COMMAND}


class CommandResponse(object):
    """
    Object to return a command response.
    """

    def get_command(self):
        """
        Returns the command.
        """
        return self.__command__

    def get_message(self):
        """
        Returns the message
        """
        if self.__message__ is None:
            return ""

        return self.__message__

    def __init__(self, command, message):
        if command in VALID_COMMANDS:
            self.__command__ = command
        else:
            self.__command__ = text.HELP_COMMAND

        self.__message__ = message


# Main business logic of the HangarBuddy
# Takes the incoming texts, figures out
# if they should be acted on,
# handles the response.
class CommandProcessor(object):
    """
    Class to control a power relay based on SMS commands.
    """

    ##############################
    #--- Public functions
    ##############################

    def run_hangar_buddy(self):
        """
        Service loop to run the HangarBuddy
        """
        self.__logger__.log_info_message('Press Ctrl-C to quit.')

        # This can be safely used off the main thread.
        # and writes into the MPqueue...
        # It kicks off every 30 seconds

        RecurringTask("monitor_gas_sensor", 30,
                      self.__monitor_gas_sensor__, self.__logger__)

        RecurringTask("battery_check", 60 * 5,
                      self.__monitor_fona_health__, self.__logger__)

        RecurringTask("update_lcd", 5, self.__update_lcd__, self.__logger__)

        # The main service loop
        while True:
            self.__run_servicer__(self.__service_gas_sensor_queue__,
                                  "Gas sensor queue")
            self.__relay_controller__.update()
            self.__run_servicer__(self.__process_pending_text_messages__,
                                  "Incoming request queue")
            self.__fona_manager__.update()

    def is_gas_detected(self):
        """
        Returns True if gas is detected.
        """
        if self.__sensors__.current_gas_sensor_reading is not None:
            return self.__sensors__.current_gas_sensor_reading.is_gas_detected

        return False

    def is_allowed_phone_number(self, phone_number):
        """
        Returns True if the phone number is allowed in the whitelist.
        """

        if phone_number is None:
            return False

        for allowed_number in self.__configuration__.allowed_phone_numbers:
            self.__logger__.log_info_message(
                "Checking " + phone_number + " against " + allowed_number)
            # Handle phone numbers that start with "1"... sometimes
            if allowed_number in phone_number or phone_number in allowed_number:
                self.__logger__.log_info_message(phone_number + " is allowed")
                return True

        self.__logger__.log_info_message(phone_number + " is denied")
        return False

    def __init__(self, buddy_configuration, logger):
        """
        Initialize the object.
        """

        self.__configuration__ = buddy_configuration
        self.__logger__ = logger
        self.__lcd_status_id__ = 0
        self.__initialize_lcd__()
        self.__is_gas_detected__ = False
        self.__system_start_time__ = time.time()
        self.__sensors__ = Sensors(buddy_configuration)

        serial_connection = self.__initialize_modem__()
        if serial_connection is None and not local_debug.is_debug():
            self.__logger__.log_warning_message(
                "Unable to initialize serial connection, quiting.")
            sys.exit()

        self.__fona_manager__ = FonaManager(self.__logger__,
                                            serial_connection,
                                            self.__configuration__.cell_power_status_pin,
                                            self.__configuration__.cell_ring_indicator_pin,
                                            self.__configuration__.utc_offset)

        # create heater relay instance
        self.__relay_controller__ = RelayManager(buddy_configuration, logger,
                                                 self.__heater_turned_on_callback__,
                                                 self.__heater_turned_off_callback__,
                                                 self.__heater_max_time_off_callback__)
        self.__gas_sensor_queue__ = MPQueue()

        self.__logger__.log_info_message(
            "Starting SMS monitoring and heater service")
        self.__clear_existing_messages__()

        self.__logger__.log_info_message("Begin monitoring for SMS messages")
        self.__queue_message_to_all_numbers__("HangarBuddy monitoring started."
                                              + "\n" + self.__get_help_status__())
        self.__queue_message_to_all_numbers__(self.__get_full_status__())
        self.__lcd__.clear()
        self.__lcd__.write(0, 0, "Ready")

    def __clear_existing_messages__(self):
        """
        Clear all of the existing messages off tdhe SIM card.
        Send a message if we did.
        """
        # clear out all the text messages currently stored on the SIM card.
        # We don't want old messages being processed
        # dont send out a confirmation to these numbers because we are
        # just deleting them and not processing them
        num_deleted = self.__fona_manager__.delete_messages()
        if num_deleted > 0:
            for phone_number in self.__configuration__.allowed_phone_numbers:
                self.__queue_message__(phone_number,
                                       "Old or unprocessed message(s) found on SIM Card."
                                       + " Deleting...")
            self.__logger__.log_info_message(
                str(num_deleted) + " old message cleared from SIM Card")

    ##############################
    #--- Status builders
    ##############################

    def __get_heater_status__(self):
        """
        Returns the status of the heater/relay.
        """
        if self.__relay_controller__ is None:
            return "Relay not detected."

        status_text = "Heater is "

        if self.__relay_controller__.is_relay_on():
            status_text += text.HEATER_ON_COMMAND + "\n"
            status_text += self.__relay_controller__.get_heater_time_remaining()
        else:
            status_text += text.HEATER_OFF_COMMAND

        status_text += "."

        return status_text

    def __get_fona_status__(self):
        """
        Returns the status of the Fona.
        ... both the signal and battery ...
        """
        signal_strength = self.__fona_manager__.signal_strength()
        battery = self.__fona_manager__.battery_condition()

        status = "CSQ:" + str(signal_strength.get_signal_strength()) + \
            " " + signal_strength.classify_strength()

        # Add the battery warning here so it will fit nicely
        # on the LCD screen.
        if not battery.is_battery_ok():
            status += " LOW BATTERY."

        status += "\nBAT:" + str(battery.battery_percent) + "% V:" + \
            str(battery.get_voltage() / 100)

        return status

    def __get_gas_sensor_status__(self):
        """
        Returns the status text for the gas sensor.
        """

        if self.__sensors__.current_gas_sensor_reading is None \
                or not self.__configuration__.is_mq2_enabled:
            return "Gas sensor NOT enabled."

        status_text = "Gas reading=" + \
            str(self.__sensors__.current_gas_sensor_reading.current_value)

        if self.__sensors__.current_gas_sensor_reading.is_gas_detected:
            status_text += "\nDANGER! GAS DETECTED!"

        return status_text

    def __get_temp_probe_status__(self):
        """
        Returns the status of the temperature probe.
        """

        if self.__sensors__.current_temperature_sensor_reading is not None:
            return "TEMP: " \
                   + str(self.__sensors__.current_temperature_sensor_reading) + "F"

        return "Temp probe not enabled."

    def __get_uptime_status__(self):
        """
        Gets how long the system has been up.
        """

        uptime = time.time() - self.__system_start_time__
        return utilities.get_time_text(uptime)

    def __get_light_status__(self):
        """
        Classifies the hangar brightness.
        """

        if self.__sensors__.current_light_sensor_reading is not None:
            status = str(int(self.__sensors__.current_light_sensor_reading.lux)) + \
                " LUX of light.\n"
            status += "Hangar is "
            brightness = "Bright. Lights on?"

            # Determine the brightness
            if self.__sensors__.current_light_sensor_reading.lux <= \
                    self.__configuration__.hangar_dark:
                brightness = "dark."
            elif self.__sensors__.current_light_sensor_reading.lux <= \
                    self.__configuration__.hangar_dim:
                brightness = "dim."
            elif self.__sensors__.current_light_sensor_reading.lux <= \
                    self.__configuration__.hangar_lit:
                brightness = "lit."

            status += brightness

            return status

        return "Light sensor not enabled."

    def __get_full_status__(self):
        """
        Returns the status of the HangarBuddy.
        This is the full status text.
        """

        try:
            status = self.__get_heater_status__() + "\n"
            status += self.__get_gas_sensor_status__() + "\n"
            status += self.__get_light_status__() + "\n"
            status += self.__get_temp_probe_status__() + "\n"
            status += self.__get_fona_status__() + "\n"
            status += self.__get_uptime_status__()
        except:
            status += "ERROR"

        return status

    def __get_help_status__(self):
        """
        Returns the message for help.
        Uses the list of valid commands to build
        the response.
        """
        status_text = "HangarBuddy commands:\n"

        for valid_command in VALID_COMMANDS:
            status_text += valid_command + "\n"

        return status_text

    ##############################
    #-- Event callbacks
    ##############################

    def __heater_turned_on_callback__(self):
        """
        Callback that signals the relay turned the heater on.
        """
        self.__queue_message_to_all_numbers__(
            "Heater turned  " + text.HEATER_ON_COMMAND + ".")

    def __heater_turned_off_callback__(self):
        """
        Callback that signals the relay turned the heater off.
        """
        self.__queue_message_to_all_numbers__(
            "Heater turned  " + text.HEATER_OFF_COMMAND + ".")

    def __heater_max_time_off_callback__(self):
        """
        Callback that signals the relay turned the heater off due to the timer.
        """
        self.__queue_message_to_all_numbers__(
            "Heater turned  " + text.HEATER_OFF_COMMAND + " due to timer.")

    ##############################
    #-- Message queing
    ##############################

    def __queue_message__(self, phone_number, message):
        """
        Puts a request to send a message into the queue.
        """
        if self.__fona_manager__ is not None and phone_number is not None and message is not None:
            self.__logger__.log_info_message(
                "MSG - " + phone_number + " : " + utilities.escape(message))
            if not self.__configuration__.test_mode:
                self.__fona_manager__.send_message(phone_number, message)

            return True

        return False

    def __queue_message_to_all_numbers__(self, message):
        """
        Puts a request to send a message to all numbers into the queue.
        """

        for phone_number in self.__configuration__.allowed_phone_numbers:
            self.__queue_message__(phone_number, message)

        return message

    ##############################
    #-- Request handlers
    ##############################

    def __handle_on_request__(self, phone_number):
        """
        Handle a request to turn on.
        """

        if phone_number is None:
            return CommandResponse(text.ERROR,
                                   "Phone number was empty.")

        self.__logger__.log_info_message(
            "Received ON request from " + phone_number)

        if self.__relay_controller__.is_relay_on():
            return CommandResponse(text.NOOP,
                                   "Heater is already ON, "
                                   + self.__relay_controller__.get_heater_time_remaining())

        if self.is_gas_detected():
            return CommandResponse(text.HEATER_OFF_COMMAND,
                                   "Gas warning. Not turning heater on")

        return CommandResponse(text.HEATER_ON_COMMAND,
                               "Heater turning on for "
                               + str(self.__configuration__.max_minutes_to_run)
                               + " minutes.")

    def __handle_off_request__(self, phone_number):
        """
        Handle a request to turn off.
        """

        self.__logger__.log_info_message(
            "Received OFF request from " + phone_number)

        if self.__relay_controller__.is_relay_on():
            try:
                return CommandResponse(text.HEATER_OFF_COMMAND,
                                       "Turning heater off with "
                                       + self.__relay_controller__.get_heater_time_remaining())
            except:
                return CommandResponse(text.ERROR,
                                       "Issue turning Heater OFF")

        return CommandResponse(text.NOOP,
                               "Heater is already OFF")

    def __handle_status_request__(self, phone_number):
        """
        Handle a status request.
        """
        self.__logger__.log_info_message(
            "Received STATUS request from " + phone_number)

        return CommandResponse(text.FULL_STATUS_COMMAND, self.__get_full_status__())

    def __handle_help_request__(self, phone_number):
        """
        Handle a help request.
        """
        self.__logger__.log_info_message(
            "Received HELP request from " + phone_number)

        return CommandResponse(text.HELP_COMMAND, self.__get_help_status__())

    def __handle_uptime_request__(self, phone_number):
        """
        Handle a request for system stats.
        """

        return CommandResponse(text.UPTIME_COMMAND, self.__get_uptime_status__())

    def __handle_quit_request__(self, phone_number):
        """
        Handle a request to quit the process.
        """

        return CommandResponse(text.QUIT_COMMAND, text.QUIT_COMMAND)

    def __handle_gas_request__(self, phone_number):
        """
        Handle a request to find out about any gas in the hangar.
        """

        return CommandResponse(text.GAS_COMMAND, self.__get_gas_sensor_status__())

    def __handle_temperature_request__(self, phone_number):
        """
        Handle a reest to find out the temperature.
        """

        return CommandResponse(text.TEMPERATURE_COMMAND, self.__get_temp_probe_status__())

    def __handle_cell_status_request__(self, phone_number):
        """
        Handle a request to find out the cell/fona status.
        """

        return CommandResponse(text.CELL_STATUS_COMMAND, self.__get_fona_status__())

    def __handle_lights_request__(self, phone_number):
        """
        Handle a request to know the status of the lights.
        """

        return CommandResponse(text.LIGHTS_COMMAND, self.__get_light_status__())

    def __handle_shutdown_request__(self, phone_number):
        """
        Handle a request to shutdown.
        """

        return CommandResponse(text.SHUTDOWN_COMMAND,
                               "Received SHUTDOWN request from "
                               + phone_number)

    def __handle_restart_request__(self, phone_number):
        """
        Handle a request to restart.
        """
        self.__logger__.log_info_message("Got restart request")
        return CommandResponse(text.RESTART_COMMAND,
                               "Restart request from " + phone_number)

    def __get_command_response__(self, message, phone_number):
        """
        Returns a command response based on the message.
        """

        cleansed_message = utilities.escape(message).upper()

        command_handlers = {
            text.FULL_STATUS_COMMAND: self.__handle_status_request__,
            text.HELP_COMMAND: self.__handle_help_request__,
            text.LIGHTS_COMMAND: self.__handle_lights_request__,
            text.CELL_STATUS_COMMAND: self.__handle_cell_status_request__,
            text.TEMPERATURE_COMMAND: self.__handle_temperature_request__,
            text.UPTIME_COMMAND: self.__handle_uptime_request__,
            text.GAS_COMMAND: self.__handle_gas_request__,
            text.SHUTDOWN_COMMAND: self.__handle_shutdown_request__,
            text.RESTART_COMMAND: self.__handle_restart_request__,
            text.QUIT_COMMAND: self.__handle_quit_request__,
            text.HEATER_OFF_COMMAND: self.__handle_off_request__,
            text.HEATER_ON_COMMAND: self.__handle_on_request__,
        }

        # Execute the first handler found.
        for command in command_handlers:
            if command.upper() in cleansed_message:
                return command_handlers[command](phone_number)

        return CommandResponse(text.HELP_COMMAND, "INVALID COMMAND\n" + self.__get_help_status__())

    def __handle_gas_ok__(self, gas_sensor_status):
        """
        Handle an "OK" message from the sensor.
        """

        if self.__is_gas_detected__:
            cleared_message = "Gas warning cleared. " + gas_sensor_status
            self.__queue_message_to_all_numbers__(cleared_message)
            self.__logger__.log_info_message(
                "Turning detected flag off.")
            self.__is_gas_detected__ = False

    def __handle_gas_warning__(self, gas_sensor_status):
        """
        Handle a gas warning from the gas sensor.
        """
        if not self.__is_gas_detected__:
            gas_status = gas_sensor_status

            if self.__relay_controller__.is_relay_on():
                gas_status += "SHUTTING HEATER DOWN"

            self.__queue_message_to_all_numbers__(gas_status)
            self.__logger__.log_warning_message(
                "Turning detected flag on.")
            self.__is_gas_detected__ = True

        # Force the heater off command no matter
        # what we think the status is.
        self.__relay_controller__.turn_off()

    ##############################
    #-- Command execution
    ##############################

    def __execute_command__(self, command_response):
        """
        Executes the action the controller has determined.
        """
        # The commands "Help", "Status", and "NoOp"
        # only send responses back to the caller
        # and do not change the heater relay
        # or the Pi
        if command_response.get_command() == text.SHUTDOWN_COMMAND:
            try:
                # Update the LCD, then set it to NULL
                # so that it will not be updated again
                self.__lcd__.write_text("Shutting down...")
                self.__lcd__ = None
                self.__queue_message_to_all_numbers__(
                    "Shutting down Raspberry Pi.")
                self.__shutdown__()

                return True
            except:
                self.__logger__.log_warning_message(
                    "CR: Issue shutting down Raspberry Pi")
        elif command_response.get_command() == text.RESTART_COMMAND:
            try:
                # Show that we are rebooting
                self.__lcd__.write_text("Restarting...")
                seld.__lcd__ = None
                self.__queue_message_to_all_numbers__("Attempting restart")
                self.__restart__()

                return True
            except:
                self.__logger__.log_warning_message(
                    "CR: Issue restarting")
        elif command_response.get_command() == text.QUIT_COMMAND:
            try:
                self.__lcd__.write_text("Quiting")
                exit()
            except:
                self.__logger__.log_warning_message(
                    "ERROR trying to quit."
                )
        elif command_response.get_command() == text.HEATER_OFF_COMMAND:
            self.__logger__.log_info_message("CR: Turning heater OFF")
            self.__relay_controller__.turn_off()

            return True
        elif command_response.get_command() == text.HEATER_ON_COMMAND:
            self.__logger__.log_info_message("CR: Turning heater ON")
            self.__relay_controller__.turn_on()

            return True

        return False

    def __process_message__(self, message, phone_number):
        """
        Process a SMS message/command.
        """

        message = message.lower()
        self.__logger__.log_info_message("Processing message:" + message)

        phone_number = utilities.get_cleaned_phone_number(phone_number)

        # check to see if this is an allowed phone number
        if not self.is_allowed_phone_number(phone_number):
            unauth_message = "Received unauthorized SMS from " + phone_number
            return self.__queue_message_to_all_numbers__(unauth_message)

        if len(phone_number) < 7:
            invalid_number_message = "Attempt from invalid phone number " + \
                phone_number + " received."
            return self.__queue_message_to_all_numbers__(invalid_number_message)

        message_length = len(message)
        if message_length < 1 or message_length > 32:
            invalid_message = "Message was invalid length."
            self.__queue_message__(
                phone_number, invalid_message)
            return self.__logger__.log_warning_message(invalid_message)

        command_response = self.__get_command_response__(
            message, phone_number)
        self.__logger__.log_info_message("Got command response")
        state_changed = self.__execute_command__(command_response)
        self.__logger__.log_info_message("executed command.")

        self.__queue_message__(
            phone_number, command_response.get_message())
        self.__logger__.log_info_message(
            "Sent message: " + command_response.get_message() + " to " + phone_number)

        return command_response.get_message(), state_changed

    def __restart__(self):
        """
        Restarts the Pi
        """
        self.__logger__.log_info_message("RESTARTING. Turning off relay")
        self.__relay_controller__.turn_off()
        utilities.restart()

    def __shutdown__(self):
        """
        Shuts down the Pi
        """
        self.__logger__.log_info_message("SHUTDOWN: Turning off relay.")
        self.__relay_controller__.turn_off()

        self.__logger__.log_info_message(
            "SHUTDOWN: Shutting down HangarBuddy.")
        utilities.shutdown()

    def __clear_queue__(self, queue):
        """
        Clears a given queue.
        """
        if queue is None:
            return False

        while not queue.empty():
            self.__logger__.log_info_message("cleared message from queue.")
            queue.get()

    ##############################
    #-- Recurring thread tasks
    ##############################

    def __monitor_gas_sensor__(self):
        """
        Monitor the Gas Sensors. Sends a warning message if gas is detected.
        """

        # Since it is not enabled... then no reason to every
        # try again during this run
        if self.__sensors__.current_gas_sensor_reading is None:
            return

        detected = self.__sensors__.current_gas_sensor_reading.is_gas_detected
        current_level = self.__sensors__.current_gas_sensor_reading.current_value

        self.__logger__.log_info_message("Detected: " + str(detected) +
                                         ", Level=" + str(current_level))

        # If gas is detected, send an immediate warning to
        # all of the phone numberss
        if detected:
            self.__clear_queue__(self.__gas_sensor_queue__)

            status = "WARNING!! GAS DETECTED!!! Level = " + \
                str(current_level)

            if self.__relay_controller__.is_relay_on():
                status += ", TURNING HEATER OFF."
                # clear the queue if it has a bunch of no warnings in it

            self.__logger__.log_warning_message(status)
            self.__gas_sensor_queue__.put(
                text.GAS_WARNING + ", level=" + str(current_level))
            self.__logger__.heater_queue.put(text.HEATER_OFF_COMMAND)
            self.__queue_message_to_all_numbers__(status)
        else:
            self.__logger__.log_info_message("Sending OK into queue", False)
            self.__gas_sensor_queue__.put(
                text.GAS_OK + ", level=" + str(current_level))

    def __monitor_fona_health__(self):
        """
        Check to make sure the Fona battery and
        other health signals are OK.
        """

        cbc = self.__fona_manager__.battery_condition()

        self.__logger__.log_info_message("GSM Battery="
                                         + str(cbc.get_percent_battery()) + "% Volts="
                                         + str(cbc.get_voltage()))

        if not cbc.is_battery_ok():
            low_battery_message = "WARNING: LOW BATTERY for Fona. Currently " + \
                str(cbc.get_percent_battery()) + "%"
            self.__queue_message_to_all_numbers__(low_battery_message)
            self.__logger__.log_warning_message(low_battery_message)

    def __update_lcd__(self):
        """
        Updates the LCD screen.
        """

        # If we start shutting down or rebooting
        # then __lcd__ is set to None to avoid
        # any more updates
        if self.__lcd__ is None:
            return

        self.__lcd__.clear()

        # Moves to the next status message based on the
        # interval in given to RecurringEvent (Normally 5 seconds)
        try:
            if self.__lcd_status_id__ == 0:
                self.__lcd__.write_text(self.__get_fona_status__())
            elif self.__lcd_status_id__ == 1:
                self.__lcd__.write_text(self.__get_heater_status__())
            elif self.__lcd_status_id__ == 2:
                self.__lcd__.write_text(self.__get_gas_sensor_status__())
            elif self.__lcd_status_id__ == 3:
                self.__lcd__.write_text(self.__get_light_status__())
            elif self.__lcd_status_id__ == 4:
                self.__lcd__.write_text(self.__get_temp_probe_status__())
            else:
                self.__lcd_status_id__ = -1
                self.__lcd__.write(0, 0, "UPTIME:")
                self.__lcd__.write(0, 1, self.__get_uptime_status__())
        except:
            self.__lcd__.write(0, 0, "ERROR: LCD_ID=" +
                               str(self.__lcd_status_id__))

        self.__lcd_status_id__ = self.__lcd_status_id__ + 1

    ##############################
    #-- Initializers
    ##############################

    def __initialize_modem__(self, retries=4, seconds_between_retries=10):
        """
        Attempts to initialize the modem over the serial port.
        """

        serial_connection = None

        if local_debug.is_debug():
            return None

        while retries > 0 and serial_connection is None:
            try:
                self.__logger__.log_info_message(
                    "Opening on " + self.__configuration__.cell_serial_port)

                serial_connection = serial.Serial(
                    self.__configuration__.cell_serial_port,
                    self.__configuration__.cell_baud_rate)
            except:
                self.__logger__.log_warning_message(
                    "SERIAL DEVICE NOT LOCATED."
                    + " Try changing /dev/ttyUSB0 to different USB port"
                    + " (like /dev/ttyUSB1) in configuration file or"
                    + " check to make sure device is connected correctly")

                # wait 60 seconds and check again
                time.sleep(seconds_between_retries)

            retries -= 1

        return serial_connection

    def __initialize_lcd__(self):
        """
        Initializes the display.
        """
        self.__lcd_status_id__ = 0
        self.__lcd__ = LcdDisplay()
        self.__lcd__.clear()
        self.__lcd__.write(0, 0, "Initializing...")

    ##############################
    #-- Servicers
    ##############################

    def __service_gas_sensor_queue__(self):
        """
        Runs the service code for messages coming
        from the gas sensor.
        """

        try:
            while not self.__gas_sensor_queue__.empty():
                gas_sensor_status = self.__gas_sensor_queue__.get()

                if gas_sensor_status is None:
                    self.__logger__.log_warning_message("Gas sensor was None.")
                else:
                    self.__logger__.log_info_message(
                        "Q:" + gas_sensor_status, False)

                if text.GAS_WARNING in gas_sensor_status:
                    self.__handle_gas_warning__(gas_sensor_status)
                elif text.GAS_OK in gas_sensor_status:
                    self.__handle_gas_ok__(gas_sensor_status)
        except Queue.Empty:
            pass

        return self.__is_gas_detected__

    def __process_pending_text_messages__(self):
        """
        Processes any messages sitting on the sim card.
        """
        # Check to see if the RI pin has been
        # tripped, or is it is time to poll
        # for messages.
        if not self.__fona_manager__.is_message_waiting():
            return False

        # Get the messages from the sim card
        messages = self.__fona_manager__.get_messages()
        total_message_count = len(messages)
        messages_processed_count = 0

        # Check to see if a mesage
        # changes the status of the system and then
        # break the processing so the queue can then
        # actually change the state.
        if total_message_count > 0:
            # Sort these messages so they are processed
            # in the order they were sent.
            # The order of reception by the GSM
            # chip can be out of order.
            sorted_messages = sorted(messages, key=lambda message: message.sent_time)

            for message in sorted_messages:
                messages_processed_count += 1
                self.__fona_manager__.delete_message(message)

                if message.minutes_waiting() > self.__configuration__.oldest_message:
                    old_message = "MSG too old, " + \
                        str(message.minutes_waiting()) + " minutes old."
                    self.__queue_message_to_all_numbers__(old_message)
                    continue

                response, state_changed = self.__process_message__(
                    message.message_text, message.sender_number)
                self.__logger__.log_info_message(response)

                # If the command did something to the unit
                # stop processing other commands
                if state_changed:
                    break

            self.__logger__.log_info_message(
                "Found " + str(total_message_count)
                + " messages, processed " + str(messages_processed_count))

        return total_message_count > 0

    def __run_servicer__(self, service_callback, service_name):
        """
        Calls and handles something with a servicer.
        """

        if service_callback is None:
            self.__logger__.log_warning_message(
                "Unable to service " + service_name)

        try:
            service_callback()
        except KeyboardInterrupt:
            print "Stopping due to CTRL+C"
            exit()
        except:
            self.__logger__.log_warning_message(
                "Exception while servicing " + service_name)
            print "Error:", sys.exc_info()[0]


##################
### UNIT TESTS ###
##################


def test_invalid_command():
    """ Test invalid commands into the response. """
    command_response = CommandResponse("INVALID", "INVALID")
    assert command_response.get_command() == text.HELP_COMMAND
    assert command_response.get_message() == "INVALID"


def test_valid_commands():
    """ Test that valid commands come back as they should. """
    for command in VALID_COMMANDS:
        message = "2061234567 " + command + " message."
        print "Testing " + command + " " + message
        command_response = CommandResponse(command, message)
        assert command_response.get_command() == command
        assert command_response.get_message() == message


#############
# SELF TEST #
#############
if __name__ == '__main__':
    import doctest
    import logging
    import configuration

    print "Starting tests."

    doctest.testmod()
    CONFIG = configuration.Configuration()

    CONTROLLER = CommandProcessor(
        CONFIG, Logger(logging.getLogger("Controller")))

    CONTROLLER.run_hangar_buddy()

    print "Tests finished"
    exit()
