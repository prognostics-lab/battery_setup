import logging
import threading
import time
from collections import namedtuple

import numpy as np
from pymeasure.adapters import SerialAdapter
from pymeasure.instruments import Instrument, SCPIMixin
from pymeasure.instruments.validators import truncated_range

log = logging.getLogger(__name__)


class Clicker(SCPIMixin, Instrument):
    gone = False

    CT = Instrument.control(
        "RCT",
        "SCT%d",
        """Sets the current plate temperature in degrees Celsius.""",
        validator=truncated_range,
        values=[10, 350],
        cast=int,
    )

    TT = Instrument.control(
        "RTT",
        "STT%d",
        """Sets the target plate temperature in degrees Celsius.""",
        validator=truncated_range,
        values=[10, 350],
        cast=int,
    )

    def __init__(
        self,
        adapter: str,
        name: str = "ESP8266 Clicker",
        baudrate: int = 115200,
        timeout: float = 0.15,
        includeSCPI=False,
        **kwargs
    ):
        adapter = SerialAdapter(port=adapter, baudrate=baudrate, timeout=timeout,
                                read_termination='\r\n', write_termination='\n')
        super().__init__(
            adapter,
            name=name,
            includeSCPI=includeSCPI,
            **kwargs
        )
        log.info(f"{self.name} initialized on port {adapter} at {baudrate} baud.")

    def go(self):
        """Sends the 'GO' command to the clicker, setting the plate temperature
        to the target temperature. Only sends the command if the 'gone' flag is
        False.
        """
        if not self.gone:
            self.write('GO')
            self.gone = True

    def set_target_temperature(self, T: int):
        """Sets the target temperature for the clicker. Sets the 'gone' flag to
        False.

        :param T: The target temperature in degrees Celsius.
        """
        self.TT = int(T)
        self.gone = False

    def shutdown(self):
        self.adapter.close()
        super().shutdown()


class SerialSensor(SCPIMixin, Instrument):
    """Instrument class for a serial sensor using PyMeasure's
    SerialAdapter.
    """

    def __init__(
        self,
        adapter: str,
        name: str,
        data_structure: dict,
        data_columns: list = None,
        baudrate: int = 115200,
        timeout: float = 0.15,
        includeSCPI=False,
        **kwargs
    ):
        """Initializes a sensor connected via serial communication.

        :param port: The serial port where the Arduino is connected \
            (e.g., '/dev/ttyACM0' or 'COM6').
        :param name: The name of the instrument.
        :param data_structure: Dictionary where keys are parameter names and \
            values are parameter types, detailing the structure of the data.
        :param baudrate: The baud rate for serial communication.
        :param timeout: Read timeout in seconds.
        :param includeSCPI: Flag indicating whether to include SCPI commands.
        :param kwargs: Additional keyword arguments.
        """
        adapter = SerialAdapter(port=adapter, baudrate=baudrate, timeout=timeout)
        super().__init__(
            adapter,
            name=name,
            includeSCPI=includeSCPI,
            **kwargs
        )
        log.info(f"{self.name} initialized on port {adapter} at {baudrate} baud.")

        self._data_structure = data_structure
        keys = list(self._data_structure.keys())
        self._data_columns = data_columns or keys
        if self.overwrite_measurements() is None:
            self._data_cls = namedtuple("_data_cls", keys)
        else:
            new_keys = [keys[i] for i in self.overwrite_measurements()]
            self._data_cls = namedtuple("_data_cls", new_keys)
        self.data = None

        self.timeout = timeout
        self._stop_thread = False
        self._thread = threading.Thread(target=self._get_meas)
        self._thread.daemon = True
        self._thread.start()
        # TODO: generalize threaded measurement for other instruments

    def __getattr__(self, name: str):
        # Only called if `name` is not found through usual means
        return getattr(self.data, name)

    @property
    def data_columns(self):
        """Names of each data element"""
        return self._data_columns

    def _get_meas(self):
        try:
            while not self._stop_thread:
                result = self.read_measurement()
                if result is not None:
                    self.data = self._data_cls(*result)
                time.sleep(0.001)
        except Exception as e:
            log.critical(f"{self.name} measurement thread failed: {e}")

    def read_measurement(self):
        """Reads measurements from serial sensor.

        :return: tuple of parsed measurements or None if error
        """
        self.write('R')
        line = ''
        start_time = time.time()
        while True:
            # Read available data without blocking
            data = self.adapter.connection.read_all().decode('ascii', errors='ignore')
            if data:
                line += data
                if '\r\n' in line:
                    line = line.strip()
                    break
            if time.time() - start_time > self.timeout:
                return None
            time.sleep(0.001)  # Sleep briefly to prevent CPU overload
        if line == "ERROR":
            log.error("Fault detected in serial sensor.")
            return None
        try:
            result = line.split(",")
            # In Python>=3.7 dicts preserve insertion order
            return {
                key: data_type(val)
                for (val, (key, data_type)) in zip(result, self._data_structure.items())
            }
        except ValueError:
            return None

    @staticmethod
    def overwrite_measurement_order():
        """Can be overridden to overwrite order of measurements. Only exists
        for retrocompatibility.
        """
        return None

    def shutdown(self):
        """Safely shuts down the serial connection.
        """
        self._stop_thread = True
        self._thread.join()
        self.adapter.close()
        super().shutdown()


class PT100SerialSensor(SerialSensor):
    """Instrument class for the PT100 temperature sensor using PyMeasure's
    SerialAdapter.
    """
    DATA_COLUMNS = ['Plate T (degC)', 'Ambient T (degC)',  'Clock (ms)']
    DATA_STRUCTURE = {
        "clock": int,
        "plate_temp": float,
        "ambient_temp": float,
    }

    def __init__(
        self,
        adapter: str,
        name: str = "PT100 Sensor",
        baudrate: int = 115200,
        timeout: float = 0.15,
        includeSCPI=False,
        **kwargs
    ):
        """Initializes the PT100 sensor connected via serial communication.

        :param port: The serial port where the Arduino is connected \
            (e.g., '/dev/ttyACM0' or 'COM6').
        :param name: The name of the instrument.
        :param baudrate: The baud rate for serial communication
        :param timeout: Read timeout in seconds
        :param includeSCPI: Flag indicating whether to include SCPI commands.
        :param kwargs: Additional keyword arguments.
        """
        adapter = SerialAdapter(port=adapter, baudrate=baudrate, timeout=timeout)
        super().__init__(
            adapter,
            name=name,
            data_structure=self.DATA_STRUCTURE,
            includeSCPI=includeSCPI,
            **kwargs
        )

    @staticmethod
    def overwrite_measurement_order():
        # plate_temp, ambient_temp, clock
        return (1, 2, 0)
