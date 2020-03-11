#!/usr/bin/env python3
from typing import List, Dict, Union
from cmd2 import Cmd
import shlex
import time
import os
import re

import htb.machine


class Service(object):
    """ Holds service information """

    def __init__(self):
        """ Initialize blank service """
        self.host: str = ""
        self.port: int = 0
        self.name: str = "blank"
        self.state: str = "closed"
        self.protocol: str = "none"

    @classmethod
    def from_masscan(cls, data: str):
        """ Build service from a line of greppable masscan results """

        # Grab the last column
        service_data = data.split(" ")[-1].split("/")

        self = Service()
        self.port = int(service_data[0])
        self.state = service_data[1]
        self.protocol = service_data[2]
        self.name = service_data[4]
        self.host = data.split("Host: ")[1].split(" ")[0]

        return self


class Scanner(object):
    """ Generic service/port scanner """

    def __init__(
        self, name: str, ports: List[int], regex: List[str], protocol: List[str]
    ):
        super(Scanner, self).__init__()

        self.name: str = name
        self.ports: List[int] = ports
        self.regex: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE) for p in regex if isinstance(p, str)
        ]
        self.protocol: List[str] = protocol

    def match(self, service: Service) -> bool:
        """ Match this scanner to a service. Returns true if it matches """

        # Protocol has to match
        if service.protocol not in self.protocol:
            return False

        # Exact port match
        if service.port in self.ports:
            return True

        # Regular expression service match
        if any([r.match(service.name) for r in self.regex]):
            return True

        return False

    def scan(self, path, hostname, machine, service: Service) -> None:
        """ Scan the service on this host """
        return


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
        self, path: str, hostname: str, machine: htb.machine.Machine, service: Service
    ) -> None:
        """ Scan the host with nikto """

        # Build appropriate URL
        if "https" in service.name:
            url = f"https://{hostname}:{service.port}"
        else:
            url = f"http://{hostname}:{service.port}"

        output_path = shlex.quote(os.path.join(path, "scans", "nikto.txt"))
        url = shlex.quote(url)

        os.system(f"nikto -host {url} -output {output_path}")


def scan(repl: Cmd, path: str, hostname: str, machine: htb.machine.Machine) -> None:
    """ Perform initial preliminary scans on the host """

    scanners = [NiktoScanner()]

    if not machine.spawned:

        repl.pwarning(f"[!] {machine.name}: not started. Start it? (Y/n) ", end="")
        resp = repl.read_input("")

        if resp.lower() == "n":
            repl.pwarning("[!] not starting machine; aborting")
            return

        if repl.cnxn.assigned is not None and repl.cnxn.assigned.id != machine.id:
            repl.pwarning(
                f"[!] {repl.cnxn.assigned.name} currently assigned. Stop it? (Y/n) ",
                end="",
            )
            resp = repl.read_input("")

            if resp.lower() == "n":
                repl.pwarning("[!] cannot start machine; aborting")
                return

            repl.poutput(f"[+] {repl.cnxn.assigned.name}: requesting termination")
            repl.cnxn.assigned.spawned = False

            repl.poutput("[+] waiting for machine termination or transfer...")

            # Save ID to re-request status
            assigned = repl.cnxn.assigned
            machine_id = machine.id

            # Wait for machine shutdown
            while True:
                # Ensure we re-request status
                repl.cnxn.invalidate_cache()

                # Check if we no longer have an assigned machine
                if repl.cnxn.assigned is None:
                    repl.poutput(f"[+] {assigned.name}: stopped or transferred!")
                    machine = repl.cnxn[machine_id]
                    break

                # Someone cancelled our termination, doing this again should relinquish
                # control from us.
                if not repl.cnxn.assigned.terminating:
                    repl.poutput(
                        f"[+] {assigned.name}: termination cancelled; trying again..."
                    )
                    repl.cnxn.assigned.terminating = True

                # We don't need a tight loop
                time.sleep(10)

        # Spawn the machine
        repl.poutput(f"[+] {machine.name}: starting...")
        machine.spawned = True

    # Wait for the machine to respond to a ping
    repl.poutput(f"[+] waiting for machine to respond to ping")
    while True:
        if os.system(f"ping -c1 {shlex.quote(hostname)} >/dev/null") == 0:
            repl.poutput(f"[+] got a ping!")
            break
        time.sleep(2)

    # Wait a couple seconds to make sure the services are up
    repl.poutput(f"[+] sleeping to allow time for services to start")
    time.sleep(10)

    # Make hostname safe for calls
    hostname = shlex.quote(hostname)

    # Run a fast all ports scan for TCP
    repl.poutput(f"[+] running tcp all ports scan w/ masscan")
    result = os.system(
        f"sudo masscan {shlex.quote(machine.ip)} -p 0-65535 --max-rate 1000 -oG {shlex.quote(os.path.join(path, 'scans', 'masscan-tcp.grep'))} -e tun0"
    )

    # Notify on error and abort
    if result != 0:
        repl.perror(f"[!] masscan failed with code: {result}")
        return

    # Read masscan results
    with open(os.path.join(path, "scans", "masscan-tcp.grep")) as f:
        # Ignore empty lines and comments
        masscan_lines = [
            line for line in f.read().split("\n") if line != "" and line[0] != "#"
        ]

    # Parse results into a service table
    services = [Service.from_masscan(line) for line in masscan_lines if "open" in line]

    repl.poutput(f"[+] {machine.name}: found {len(services)} open ports")

    # Iterate over valid services
    for service in services:
        # Iterate over matching scanners
        for scanner in [s for s in scanners if s.match(service)]:
            repl.pwarning(f"[?] run matching scanner {scanner.name}? (Y/n) ", end="")
            if repl.read_input("").lower() == "n":
                continue
            scanner.scan(path, hostname, machine, service)

    return
