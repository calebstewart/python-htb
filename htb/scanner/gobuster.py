#!/usr/bin/env python3
import subprocess
import signal
import shlex
import time
import sys
import os

# from htb.machine import Machine
from htb.scanner.scanner import Scanner, Service, Tracker
from htb import util


class GobusterScanner(Scanner):
    """ Scan a web server with for directories/files with Gobuster """

    def __init__(self):
        super(GobusterScanner, self).__init__(
            name="gobuster",
            ports=[80, 443, 8080, 8443, 8888],
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
        """ Scan the host with gobuster """

        output_path = os.path.join(path, "scans", f"{self.ident(service)}.txt")

        wordlist = "/usr/share/dirbuster/directory-list-2.3-small.txt"
        url = f"{hostname}:{service.port}"

        # Call gobuster
        tracker.data["popen"] = subprocess.Popen(
            ["gobuster", "-w", wordlist, "-f", "-k", "-o", output_path, "-u", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=lambda: signal.signal(signal.SIGTSTP, signal.SIG_IGN),
        )

        line = b""

        while tracker.data["popen"].poll() is None:

            # Grab next byte
            data = tracker.data["popen"].stdout.read(1)

            # Not silent, output
            if not tracker.silent:
                sys.stdout.write(data.decode("utf-8"))

            if data == b"\n" or data == b"\r":
                # Set status
                if line.startswith(b"Progress:"):
                    yield line.split(b"Progress:")[1].decode("utf-8").strip()
                line = b""

                # We don't want a busy loop. Sleep after every line
                time.sleep(0.1)
            else:
                line += data

            # time.sleep(0.1)

        yield "completed"

    def cancel(self, tracker: Tracker) -> None:
        """ Ensure the running process dies """

        tracker.data["popen"].terminate()
        try:
            tracker.data["popen"].wait(timeout=1)
        except subprocess.TimeoutExpired:
            tracker.data["popen"].kill()
            tracker.data["popen"].wait()
