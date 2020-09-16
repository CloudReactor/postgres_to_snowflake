# Copyright (c) 2020, CloudReactor, Inc.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
This module allows a Task to communicate status back to CloudReactor while
it is still running. It uses UDP to send messages to the wrapper script
which buffers them and sends them to CloudReactor periodically.
Because UDP is used, status updates are not 100% reliable but in practice
since a local socket is used, the vast majority of status updates will
be send to CloudReactor.
"""

from typing import Any, Dict, Optional

import json
import logging
import os
import socket
import atexit


def _exit_handler(updater):
    """Handle exit."""
    atexit.unregister(_exit_handler)
    updater.shutdown()


class StatusUpdater:
    """
    Instances of this class are used to send status updates to CloudReactor.
    """

    DEFAULT_STATUS_UPDATE_PORT = 2373

    def __init__(self, enabled: Optional[bool] = None,
            port: Optional[int] = None,
            logger: Optional[logging.Logger] = None):
        """
        Create a new instance.

        enabled == False means this instance will not send updates to the
        wrapper script (which would send them to CloudReactor).
        If not specified, it will be read from the the
        environment variable PROC_WRAPPER_ENABLE_STATUS_UPDATE_LISTENER.
        Set it to TRUE to enable status updates.

        port is the number of the UDP port used to communicate with the wrapper script.
        If not specified, it will be read from the
        environment variable PROC_WRAPPER_STATUS_UPDATE_SOCKET_PORT, and if
        that is not present it will use port 2373.

        logger is an optional logger that will sent info() when last_status_message
        is specified in send_update().

        """
        self.internal_logger = logging.getLogger(__name__)
        self.internal_logger.addHandler(logging.NullHandler())
        self.external_logger = logger

        self.socket = None

        if port is None:
            self.port = int(os.environ.get('PROC_WRAPPER_STATUS_UPDATE_SOCKET_PORT') or
                    StatusUpdater.DEFAULT_STATUS_UPDATE_PORT)
        else:
            self.port = port

        if enabled is None:
            self.enabled = os.environ.get(
                  'PROC_WRAPPER_ENABLE_STATUS_UPDATE_LISTENER',
                  'FALSE').upper() == 'TRUE'
        else:
            self.enabled = enabled

        if self.enabled:
            self.internal_logger.info('StatusUpdater is enabled')
        else:
            self.internal_logger.info('StatusUpdater is disabled')
            return

        atexit.register(_exit_handler, self)

    def __enter__(self):
        """Implement entrypoint for python with statement."""
        return self

    def __exit__(self, _type, _value, _traceback):
        """Implement exit point for python with statement."""
        self.shutdown()

    def send_update(self, success_count: Optional[int] = None,
            error_count: Optional[int] = None,
            skipped_count: Optional[int] = None,
            expected_count: Optional[int] = None,
            last_status_message: Optional[int] = None,
            extra_props: Optional[Dict[str, Any]] = None,
            logger: Optional[logging.Logger] = None):
        """
        Send an update to the wrapping script, if this instance is enabled.
        If logger is specified, last_status_message will logged there if present.
        Otherwise, if logger was specified in __init__() it will use that logger.
        """

        resolved_logger = logger or self.external_logger
        if resolved_logger and last_status_message:
            resolved_logger.info(last_status_message)

        if not self.enabled:
            return

        status_hash: Dict[str, Any] = {}

        if success_count is not None:
            status_hash['success_count'] = success_count

        if error_count is not None:
            status_hash['error_count'] = error_count

        if skipped_count is not None:
            status_hash['skipped_count'] = skipped_count

        if expected_count is not None:
            status_hash['expected_count'] = expected_count

        if last_status_message:
            status_hash['last_status_message'] = last_status_message

        if extra_props:
            status_hash['other_runtime_metadata'] = extra_props

        message = (json.dumps(status_hash) + "\n").encode('UTF-8')

        try:
            self.reuse_or_create_socket().sendto(message, ('127.0.0.1', self.port))
        except Exception:
            self.internal_logger.debug("Can't send status update, resetting socket")
            self.shutdown()

    def shutdown(self):
        """
        Shut this instance down, reclaiming the status update socket.
        """
        if self.socket:
            self.internal_logger.info('Closing status update socket ...')
            try:
                self.socket.close()
                self.internal_logger.info('Done closing status update socket.')
            finally:
                self.socket = None

    def reuse_or_create_socket(self):
        """
        Create the socket used for communication, if not created already.
        Otherwise, reuse the previously created one.
        """
        if not self.socket:
            self.socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
            self.socket.setblocking(False)

        return self.socket
