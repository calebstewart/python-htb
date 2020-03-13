#!/usr/bin/env python3
import shlex
import subprocess
import os

from htb.machine import Machine
from htb.scanner.scanner import Scanner, Service


class GobusterScanner(Scanner):
    """ Perform directory enumeration on a web server """

    def __init__(self):
        super(GobusterScanner, self).__init__(
            name="gobuster",
            ports=[80, 8080, 443, 8443, 8000,],
            regex=[r".*http.*", r".*web.*"],
            protocol=["tcp"],
            recommended=True,
        )

    def scan(
        self, path: str, hostname: str, machine: Machine, service: Service, silent=False
    ) -> None:
        """ Scan the host with gobuster """

        # Build appropriate URL
        if "https" in service.name:
            url = f"https://{hostname}:{service.port}"
        else:
            url = f"http://{hostname}:{service.port}"

        output_path = os.path.join(path, "scans", "gobuster.txt")
        output = subprocess.DEVNULL if silent else None

        # Run gobuster
        subprocess.call(
            [
                "gobuster",
                "-w",
                "/usr/share/dirbuster/directory-list-2.3-small.txt",
                "-f",
                "-k",
                "-o",
                output_path,
                "-u",
                url,
            ],
            stdout=output,
            stderr=output,
        )
