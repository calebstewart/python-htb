#!/usr/bin/env python3
from typing import List, Dict, Any, Generator
from dataclasses import dataclass
import threading
import queue
import re

from htb.machine import Machine


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


@dataclass
class Tracker(object):
    silent: bool
    machine: Machine
    service: Service
    scanner: "Scanner"
    status: str
    events: queue.Queue
    thread: threading.Thread
    stop: bool
    data: Dict[str, Any]
    lock: threading.Lock = None


class Scanner(object):
    """ Generic service/port scanner """

    def __init__(
        self,
        name: str,
        ports: List[int],
        regex: List[str],
        protocol: List[str],
        recommended=False,
    ):
        super(Scanner, self).__init__()

        self.name: str = name
        self.ports: List[int] = ports
        self.regex: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE) for p in regex if isinstance(p, str)
        ]
        self.protocol: List[str] = protocol
        self.recommended: bool = recommended

    def ident(self, service) -> str:
        """ Get unique identifier for this service/scanner combo """
        return f"{self.name}-{service.port}-{service.protocol}"

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

    def background(
        self,
        tracker: Tracker,
        path: str,
        hostname: str,
        machine: Machine,
        service: Service,
    ) -> threading.Thread:
        """ Start the scan in the background """

        # Ensure we run silently
        # tracker.silent = True

        # Create and start the thread
        thread = threading.Thread(
            target=self._do_background_scan,
            args=(tracker, path, hostname, machine, service),
        )
        thread.start()

        # Return thread handle
        return thread

    def continue_background(
        self, tracker: Tracker, generator: Generator[str, None, None]
    ):
        """ Transfer control of a running scan to a background task """

        tracker.silent = True

        thread = threading.Thread(
            target=self._do_continue_background, args=(tracker, generator)
        )
        thread.start()

        return thread

    def _do_continue_background(
        self, tracker: Tracker, generator: Generator[str, None, None]
    ):
        """ Continue the scan in the background """

        # This ensures the main thread doesn't trample us
        tracker.lock.acquire()

        for status in generator:
            print(f"GOT STATUS {status}")
            tracker.status = status
            if tracker.stop:
                self.cancel(tracker)

        tracker.events.put(tracker)

    def _do_background_scan(
        self,
        tracker: Tracker,
        path: str,
        hostname: str,
        machine: Machine,
        service: Service,
    ) -> None:
        """ Start the scan in the background and notify the queue when it is complete """
        for status in self.scan(tracker, path, hostname, machine, service):
            # Set status
            tracker.status = status

            # The job was killed
            if tracker.stop:
                # Perform shutdown needed
                self.cancel(tracker)
                break

        with tracker.lock:
            tracker.events.put(tracker)

    def cancel(self, tracker: Tracker) -> None:
        """ Shutdown any recurring things (like killing processes) """
        return

    def scan(
        self,
        tracker: Tracker,
        path: str,
        hostname: str,
        machine: Machine,
        service: Service,
    ) -> None:
        """ Scan the service on this host """
        yield "running"
