#!/usr/bin/env python3
from typing import List, Dict, Union
from threading import Barrier
from cmd2 import Cmd
import threading
import signal
import queue
import shlex
import time
import sys
import os
import re

import htb.machine
from htb.scanner.scanner import Service, Scanner, Tracker
from htb.scanner.nikto import NiktoScanner
from htb.scanner.enum4linux import Enum4LinuxScanner
from htb.scanner.gobuster import GobusterScanner

AVAILABLE_SCANNERS = [Enum4LinuxScanner(), GobusterScanner()]


def scan(
    repl: Cmd,
    path: str,
    hostname: str,
    machine: htb.machine.Machine,
    run_recommended: bool = False,
) -> None:
    """ Perform initial preliminary scans on the host """

    if not machine.spawned:

        repl.pwarning(f"{machine.name}: not started. Start it? (Y/n) ", end="")
        sys.stderr.flush()
        resp = repl.read_input("")

        if resp.lower() == "n":
            repl.perror("not starting machine; aborting")
            return

        if repl.cnxn.assigned is not None and repl.cnxn.assigned.id != machine.id:

            if repl.cnxn.assigned.terminating:
                repl.poutput("{repl.cnxn.assigned.name} already terminating")
            else:
                repl.pwarning(
                    f"{repl.cnxn.assigned.name} currently assigned. Stop it? (Y/n) ",
                    end="",
                )
                sys.stderr.flush()
                resp = repl.read_input("")

                if resp.lower() == "n":
                    repl.perror("cannot start machine; aborting")
                    return

                repl.poutput(f"{repl.cnxn.assigned.name}: requesting termination")
                repl.cnxn.assigned.spawned = False

            repl.poutput("waiting for machine termination or transfer...")

            # Save ID to re-request status
            assigned = repl.cnxn.assigned
            machine_id = machine.id

            # Wait for machine shutdown
            while True:
                # Ensure we re-request status
                repl.cnxn.invalidate_cache()

                # Check if we no longer have an assigned machine
                if repl.cnxn.assigned is None:
                    repl.psuccess(f"{assigned.name}: stopped or transferred!")
                    machine = repl.cnxn[machine_id]
                    break

                # Someone cancelled our termination, doing this again should relinquish
                # control from us.
                if not repl.cnxn.assigned.terminating:
                    repl.pwarning(
                        f"{assigned.name}: termination cancelled; trying again..."
                    )
                    repl.cnxn.assigned.terminating = True

                # We don't need a tight loop
                time.sleep(10)

        # Spawn the machine
        repl.poutput(f"{machine.name}: starting...")
        machine.spawned = True

    # Wait for the machine to respond to a ping
    repl.poutput(f"waiting for machine to respond to ping")
    while True:
        if os.system(f"ping -c1 {shlex.quote(hostname)} >/dev/null") == 0:
            repl.psuccess(f"got a ping!")
            break
        time.sleep(2)

    # Wait a couple seconds to make sure the services are up
    repl.poutput(f"sleeping to allow time for services to start")
    time.sleep(10)

    # Make hostname safe for calls
    hostname = shlex.quote(hostname)

    # Run a fast all ports scan for TCP
    repl.psuccess(f"running tcp all ports scan w/ masscan")
    result = os.system(
        f"sudo masscan {shlex.quote(machine.ip)} -p 80 --max-rate 1000 -oG {shlex.quote(os.path.join(path, 'scans', 'masscan-tcp.grep'))} -e tun0"
    )

    # masscan output messes up future prompts for some reason
    sys.stdout.write("\n")

    # Notify on error and abort
    if result != 0:
        repl.perror(f"masscan failed with code: {result}")
        return

    # Read masscan results
    with open(os.path.join(path, "scans", "masscan-tcp.grep")) as f:
        # Ignore empty lines and comments
        masscan_lines = [
            line for line in f.read().split("\n") if line != "" and line[0] != "#"
        ]

    # Parse results into a service table
    services = [Service.from_masscan(line) for line in masscan_lines if "open" in line]

    repl.psuccess(f"{machine.name}: found {len(services)} open ports")

    background_scanners = {}
    complete_queue = queue.Queue()

    # Run all recommended scanners in the background if requested
    if run_recommended:
        for service in services:
            for scanner in [
                s for s in AVAILABLE_SCANNERS if s.match(service) and s.recommended
            ]:
                repl.pwarning(
                    f"starting recommended scanner {scanner.name} in background"
                )

                # Create a tracker and the job
                tracker = Tracker(
                    True,
                    machine,
                    service,
                    scanner,
                    "running",
                    repl.job_events,
                    None,
                    False,
                    {},
                )
                tracker.thread = scanner.background(
                    tracker, path, hostname, machine, service
                )
                repl.jobs.append(tracker)

    # Iterate over valid services
    for service in services:
        # Iterate over matching scanners
        for scanner in [
            s
            for s in AVAILABLE_SCANNERS
            if s.match(service) and s.ident(service) not in background_scanners
        ]:
            repl.poutput(
                f"run matching scanner {scanner.name} for {service.port}/{service.protocol} ({service.name})? (Y/n/b) ",
                end="",
            )
            sys.stderr.flush()
            sys.stdout.flush()

            response = input("").strip()  # repl.read_input("").lower()

            if response == "n":
                continue

            # Create the tracker
            tracker = Tracker(
                False,
                machine,
                service,
                scanner,
                "running",
                repl.job_events,
                None,
                False,
                {},
                threading.Lock(),
            )

            if response == "b":
                repl.pwarning(
                    f"backgrounding {scanner.name} for {service.port}/{service.protocol}"
                )

                tracker.silent = True
                tracker.thread = scanner.background(
                    tracker, path, hostname, machine, service
                )
                repl.jobs.append(tracker)
            else:
                events = queue.Queue()
                tracker.job_events = events

                class GoToSleep(Exception):
                    pass

                def background_me(signo, stack):
                    """ Transfer running task to background thread """
                    signal.signal(signal.SIGTSTP, signal.SIG_DFL)
                    raise GoToSleep

                try:
                    signal.signal(signal.SIGTSTP, background_me)

                    tracker.thread = scanner.background(
                        tracker, path, hostname, machine, service
                    )

                    try:
                        tracker = tracker.job_events.get()
                    except KeyboardInterrupt:
                        repl.pwarning(
                            f"cancelling {scanner.name} for {service.port}/{service.protocol}"
                        )
                        tracker.stop = True

                    # Restore previous signal
                    signal.signal(signal.SIGTSTP, signal.SIG_DFL)
                except GoToSleep:
                    with tracker.lock:
                        repl.pwarning(
                            f"backgrounding {scanner.name} for {service.port}/{service.protocol}"
                        )
                        tracker.silent = True
                        tracker.job_events = repl.job_events
                        repl.jobs.append(tracker)

    return
