import logging

from ..BaseProcedure import BaseProcedure
from ..utils import Parameters
from ...utils import send_telegram_alert

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class CellProcedure(BaseProcedure):
    """Base procedure for all device-related measurements. It defines
    parameters that involve a single cell.
    """
    # Cell Parameters
    cell_id: str = Parameters.Cell.cell_id
    cell_geometry: int = Parameters.Cell.cell_geometry

    INPUTS = BaseProcedure.INPUTS + ['cell_id', 'cell_geometry']

    def shutdown(self):
        if not self.should_stop() and self.status >= self.RUNNING:
            send_telegram_alert(
                f"Finished {type(self).__name__} measurement for Cell "
                f"{self.chip_id} {self.cell_geometry}"
            )

        super().shutdown()
