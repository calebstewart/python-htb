#!/usr/bin/env python3
import subprocess
import shlex
import time
import sys
import os

from htb.machine import Machine
from htb.scanner.scanner import Scanner, Service, Tracker


class NiktoScanner(Scanner):
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
        machine: Machine,
        service: Service,
    ) -> None:
        """ Scan the host with nikto """

        output_path = os.path.join(path, "scans", f"{self.ident(service)}.txt")

        # If we are backgrounded, ignore stdout and stderr
        output = open(output_path, "w")

        url = f"http://{hostname}:{service.port}"

        # Call enum4linux
        tracker.data["popen"] = subprocess.Popen(
            ["nikto", "-ask", "no", "-output", output_path, "-host", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        while tracker.data["popen"].poll() is None:
            line = tracker.data["popen"].stdout.readline()

            # Output if not silent
            if not tracker.silent:
                sys.stdout.write(line.decode("utf-8"))

            output.write(line.decode("utf-8"))

            yield "running"

            time.sleep(0.1)

        output.close()

        yield "completed"

    def cancel(self, tracker: Tracker) -> None:
        """ Ensure the running process dies """

        tracker.data["popen"].terminate()
        try:
            tracker.data["popen"].wait(timeout=1)
        except subprocess.TimeoutExpired:
            tracker.data["popen"].kill()
            tracker.data["popen"].wait()
