#!/usr/bin/env python3
from typing import Union
import subprocess
import signal
import shlex
import time
import sys
import os

# from htb.machine import Machine
from htb.scanner.scanner import ExternalScanner, Scanner, Service, Tracker
from htb import util


class GobusterScanner(ExternalScanner):
    """ Scan a web server with for directories/files with Gobuster """

    LINE_DELIM = [b"\n", b"\r"]

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

        wordlist = machine.connection.config.get(
            "gobuster",
            "wordlist",
            fallback="/usr/share/wordlists/dirbuster/directory-list-2.3-small.txt",
        )
        url = f"{hostname}:{service.port}"

        yield from super(GobusterScanner, self).scan(
            tracker,
            path,
            hostname,
            machine,
            service,
            [
                "gobuster",
                "dir",
                "-w",
                wordlist,
                "-f",
                "-k",
                "-o",
                output_path,
                "-u",
                url,
            ],
        )

    def do_line(
        self, tracker: Tracker, scanner: Scanner, line: bytes
    ) -> Union[None, str]:
        if line.startswith(b"Progress:"):
            return line.split(b"Progress:")[1].decode("utf-8").strip()
        return None

    def cancel(self, tracker: Tracker) -> None:
        """ Ensure the running process dies """

        tracker.data["popen"].terminate()
        try:
            tracker.data["popen"].wait(timeout=1)
        except subprocess.TimeoutExpired:
            tracker.data["popen"].kill()
            tracker.data["popen"].wait()
