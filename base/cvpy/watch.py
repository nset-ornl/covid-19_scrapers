#!/usr/bin/env python3
"""Provides convenience methods to monitor a folder."""
import logging
from cvpy.slurp import Slurp
from cvpy.ingester import Ingest
from cvpy.digester import Digest
from cvpy.common import check_environment as ce
from watchdog.events import PatternMatchingEventHandler


class ScrapeHandler(PatternMatchingEventHandler):
    """This class provides a watchdog event to monitor csv file creation in the
       $INPUT_DIR directory."""
    patterns = ["*.csv"]
    logger = logging.getLogger(ce('PY_LOGGER', 'main'))

    def process(self, event):
        """Process a csv file that has been created in the $INPUT_DIR."""
        self.logger.info(f'Source Path:\t{event.src_path}\n' +
                         f'Event Type:\t{event.event_type}\n')
        Ingest(event.src_path)

    def on_created(self, event):
        """Process event when file is created."""
        self.process(event)


class DataHandler(PatternMatchingEventHandler):
    """This class provides a watchdog event to monitor for csv files in a
       directroy.
    """
    patterns = ["*.csv"]
    logger = logging.getLogger(ce('PY_LOGGER', 'main'))

    def process(self, event):
        """Process a csv file that has been created."""
        self.logger.info(f'Source Path:\t{event.src_path}\n' +
                         f'Event Type:\t{event.event_type}\n')
        Digest(event.src_path)

    def on_created(self, event):
        """Process event when file is created."""
        self.process(event)


class SlurpHandler(PatternMatchingEventHandler):
    """This class provides a watchdog event to monitor for csv files in a
       directroy.
    """
    patterns = ["*.csv"]
    logger = logging.getLogger(ce('PY_LOGGER', 'main'))

    def process(self, event):
        """Process a csv file that has been created."""
        self.logger.info(f'Source Path:\t{event.src_path}\n' +
                         f'Event Type:\t{event.event_type}\n')
        Slurp(event.src_path)

    def on_created(self, event):
        """Process event when file is created."""
        self.process(event)