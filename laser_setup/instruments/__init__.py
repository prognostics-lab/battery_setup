"""Module that includes the instruments used in the experiments.
"""
from pymeasure.adapters import FakeAdapter
from pymeasure.instruments import Instrument
from pymeasure.instruments.thorlabs import ThorlabsPM100USB

from .bentham import Bentham
from .manager import InstrumentManager, InstrumentProxy
from .keithley import Keithley2450, Keithley6517B, Keithley2460
from .serial import Clicker, SerialSensor, PT100SerialSensor
from .tenma import TENMA
