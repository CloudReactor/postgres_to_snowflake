#!/usr/local/bin/python

"""
An example task that shows how to send status updates back to CloudReactor
using the status_updater module.
"""

import logging
import os
import random
import signal
import sys
import time
from dotenv import load_dotenv

from status_updater import StatusUpdater


def signal_handler(signum, frame):
    """This will cause the exit handler to be executed, if it is registered."""
    raise RuntimeError('Caught SIGTERM, exiting.')


def make_start_message(prefix: str) -> str:
    """A testable function."""
    return prefix + ' sleeping!'

def main():
    """
    Iterate over a range of integers, sending status updates periodically.
    """

    # Load variables from the .env file into the environment. This can be used
    # to configure settings during development, as deploy/files/.env.dev mapped
    # to the .env file by Docker Compose. When deployed to ECS, .env.[deployment name]
    # will be loaded instead.
    load_dotenv()

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    signal.signal(signal.SIGTERM, signal_handler)

    num_rows = int(os.environ.get('NUM_ROWS', '5'))
    row_to_fail_at = int(os.environ.get('ROW_TO_FAIL_AT', '-1'))

    with StatusUpdater(logger=logger) as updater:
        start_message = make_start_message('I am')
        updater.send_update(last_status_message=start_message,
                            expected_count=random.randrange(5, 15))
        success_count = 0
        for i in range(num_rows):
            if i == row_to_fail_at:
                updater.send_update(error_count=1)
                logging.error("Failed on row %i, exiting!", i)
                sys.exit(1)
            else:
                logging.info("sleeping %i ...", i)
                time.sleep(2)
                success_count += random.randrange(1, 10)

                try:
                    updater.send_update(success_count=success_count)
                except Exception:
                    logging.info('Failed to send update')

                logging.info("done sleeping")

        updater.send_update(last_status_message='woken up')


if __name__ == '__main__':
    main()
