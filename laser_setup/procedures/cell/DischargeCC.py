import logging
import time

from ...instruments import InstrumentManager, Keithley2460, SerialSensor
from ...utils import get_latest_DP
from .CellProcedure import CellProcedure
from ..utils import Instruments, Parameters

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class DischargeCC(CellProcedure):
    """Discharges a cell using a CC procedure, while measuring surface and
    surrounding air temperatures at two different points.
    """

    name = "CC discharge"

    _temperature_columns = [
        "Clock (s)",
        "T° surface 1 (°C)",
        "T° surface 2 (°C)",
        "T° air 1 (°C)",
        "T° air 2 (°C)",
    ]

    # Instruments
    instruments = InstrumentManager()
    meter: Keithley2460 = instruments.queue(**Instruments.Keithley2460)
    temperature_sensor: SerialSensor = instruments.queue(
        **Instruments.SerialSensor,
        name="Temperature sensor",
        kwargs={
            "data_structure": {
                "clock": int,
                "surface1": float,
                "surface2": float,
                "air1": float,
                "air2": float,
            },
            "data_columns": _temperature_columns,
        }
    )

    # Cell parameters
    soc = Parameters.Cell.soc
    capacity = Parameters.Cell.capacity

    # Cycle parameters
    volt_limit = Parameters.Instrument.volt_limit
    Irange = Parameters.Instrument.Irange
    sampling_t = Parameters.Control.sampling_t

    # Temperature parameters
    sense_T = Parameters.Instrument.sense_T

    INPUTS = CellProcedure.INPUTS + [
        "soc",
        "capacity",
        "volt_limit",
        "Irange",
        "sampling_t",
        "sense_T",
    ]
    DATA_COLUMNS = ["t (s)", "I (A)", "V (V)", "SoC (-)", "Q (mAh)"] + _temperature_columns
    EXCLUDE = CellProcedure.EXCLUDE + ["sense_T"]
    SEQUENCER_INPUTS = ["laser_v", "vg", "target_T"]

    def connect_instruments(self):
        self.temperature_sensor = None if not self.sense_T else self.temperature_sensor
        super().connect_instruments()

    def pre_startup(self):
        # Stuff like parameter preprocessing
        log.info("Pre-startup procedure")

    def startup(self):
        log.info("Startup procedure")
        self.connect_instruments()

        # Keithley 2450 meter
        self.meter.reset()
        self.meter.make_buffer()

        # TODO: Implement Keithley controls
        # keithley_controls()

        # smu.measure.func = smu.FUNC_DC_CURRENT 	-- Se mide corriente
        # smu.measure.sense = smu.SENSE_4WIRE 	-- Se cambia el sistema de medición a 4-wire para más precisión
        # smu.source.func = smu.FUNC_DC_VOLTAGE 	-- Se controla el voltaje
        # smu.source.offmode = smu.OFFMODE_HIGHZ 	-- Modo cuando la carga de desconecta para aislar el equipo
        # smu.source.level = voltlimit-0.05 		-- Fijar inferior a voltlimit para asegurar descarga constante
        # smu.source.range = 7					-- Asegura lectura de voltaje para valores menores a 7V
        # smu.measure.terminals = smu.TERMINALS_FRONT
        # smu.source.readback = smu.ON
        # TODO: Determine if readback is necessary and what it does

        self.meter.wires = 4
        self.meter.voltage_output_off_state = "HIMP"
        self.meter.use_front_terminals()

        # TODO: Verify this implementation of electrical control
        self.meter.apply_voltage(voltage_range=self.volt_limit - 0.05)
        self.meter.measure_current(current=self.Irange)

        # self.meter.apply_voltage(compliance_current=self.Irange * 1.1 or 0.1)
        # self.meter.measure_current(
        #     current=self.Irange, nplc=self.NPLC, auto_range=not bool(self.Irange)
        # )
        # # Turn on the outputs

        self.meter.enable_source()
        time.sleep(1.0)

    def execute(self):
        log.info("Starting the measurement")
        self.meter.clear_buffer()
        done = False
        prev_time = self.meter.get_time()
        iteration = 0

        temperature_data = ()  # If temperature is measured, this gets replaced
        soc = self.soc
        charge = soc * self.capacity

        # TODO: Test if the loop is correct

        # Main loop
        while not done:
            # Handle critical stop
            if self.should_stop():
                log.warning("Measurement aborted")
                return

            # Take measurements
            voltage = self.meter.voltage
            current = self.meter.current
            time = self.meter.get_time()
            time_delta = time - prev_time
            prev_time = time

            if voltage <= self.volt_limit:
                log.info("Voltage under limit, stopping")
                break

            # Coulomb counting
            charge_change = -current * time_delta / 3.6
            charge += charge_change
            soc += charge_change / self.capacity

            # Report progress
            self.emit("progress", 100 * (1 - soc))

            if self.sense_T:
                temperature_data = self.temperature_sensor.data

            self.emit(
                "results",
                dict(
                    zip(
                        self.DATA_COLUMNS,
                        [time, current, voltage, soc, charge, *temperature_data],
                    )
                ),
            )
            time.sleep(self.sampling_t)

        log.info("Finished discharge")
