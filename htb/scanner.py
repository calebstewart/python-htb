#!/usr/bin/env python3
from cmd2 import Cmd
import shlex
import time
import os

import htb.machine


def scan(repl: Cmd, path: str, hostname: str, machine: htb.machine.Machine) -> None:
    """ Perform initial preliminary scans on the host """

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

    return
