#!/usr/bin/env python3
import subprocess
import shlex
import time
import sys
import os

# from htb.machine import Machine
from htb.scanner.scanner import Scanner, Service, Tracker


class Enum4LinuxScanner(Scanner):
    """ Scan a web server with nikto """

    def __init__(self):
        super(Enum4LinuxScanner, self).__init__(
            name="enum4linux",
            ports=[445],
            regex=[r".*smb.*", r".*microsoft-ds.*"],
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

        # Call enum4linux
        tracker.data["popen"] = subprocess.Popen(
            ["enum4linux", "-a", hostname],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        while tracker.data["popen"].poll() is None:
            line = tracker.data["popen"].stdout.readline()

            # Output if not silent
            if not tracker.silent:
                sys.stdout.write(line.decode("utf-8"))

            output.write(line.decode("utf-8"))

            # Set status
            if line.startswith(b"|"):
                yield line.split(b"|")[1].decode("utf-8").strip()

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
