#!/usr/bin/env python3
from typing import Union
import subprocess
import shlex
import time
import sys
import os

# from htb.machine import Machine
from htb.scanner.scanner import ExternalScanner, Service, Tracker, Scanner


class NiktoScanner(ExternalScanner):
    """ Scan a web server with nikto """

    def __init__(self):
        super(NiktoScanner, self).__init__(
            name="nikto",
            ports=[80, 443, 8080, 8443, 8000],
            regex=[r".*http.*", r".*web.*"],
            protocol=["tcp"],
        )

    def scan(
        self,
        tracker: Tracker,
        path: str,
        hostname: str,
        machine: "htb.machine.Machine",
        service: Service,
    ) -> None:
        """ Scan the host with nikto """

        output_path = os.path.join(path, "scans", f"{self.ident(service)}.txt")

        # If we are backgrounded, ignore stdout and stderr
        output = open(output_path, "w")

        url = f"http://{hostname}:{service.port}"

        return super(NiktoScanner, self).scan(
            tracker,
            path,
            hostname,
            machine,
            service,
            argv=["nikto", "-ask", "no", "-output", output_path, "-host", url],
        )

    def do_line(
        self, tracker: Tracker, scanner: Scanner, line: bytes
    ) -> Union[None, str]:
        """ I have no useful progress info for Nikto :( """
        return None
