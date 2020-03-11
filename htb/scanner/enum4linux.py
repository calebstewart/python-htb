#!/usr/bin/env python3
import shlex
import os

from htb.machine import Machine
from htb.scanner.scanner import Scanner, Service


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
        self, path: str, hostname: str, machine: Machine, service: Service, silent=False
    ) -> None:
        """ Scan the host with nikto """

        output_path = shlex.quote(os.path.join(path, "scans", "enum4linux.txt"))
        hostname = shlex.quote(hostname)

        redirect = f">{output_path} 2>/dev/null" if silent else f" | tee {output_path}"

        os.system(f"enum4linux -a {shlex.quote(hostname)} {redirect}")
