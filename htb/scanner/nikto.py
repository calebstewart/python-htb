#!/usr/bin/env python3
import shlex
import os

from htb.machine import Machine
from htb.scanner.scanner import Scanner, Service


class NiktoScanner(Scanner):
    """ Scan a web server with nikto """

    def __init__(self):
        super(NiktoScanner, self).__init__(
            name="nikto",
            ports=[80, 8080, 443, 8443, 8000,],
            regex=[r".*http.*", r".*web.*"],
            protocol=["tcp"],
        )

    def scan(
        self, path: str, hostname: str, machine: Machine, service: Service, silent=False
    ) -> None:
        """ Scan the host with nikto """

        # Build appropriate URL
        if "https" in service.name:
            url = f"https://{hostname}:{service.port}"
        else:
            url = f"http://{hostname}:{service.port}"

        output_path = shlex.quote(os.path.join(path, "scans", "nikto.txt"))
        url = shlex.quote(url)

        redirect = " > /dev/null 2>&1" if silent else ""

        os.system(f"nikto -host {url} -output {output_path} {redirect}")
