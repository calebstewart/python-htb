#!/usr/bin/env python3
from typing import List, Dict, Any, Generator
from dataclasses import dataclass
import subprocess
import threading
import datetime
import signal
import queue
import time
import sys
import re

# from htb.machine import Machine


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

    @classmethod
    def from_nmap(cls, data: str):
        """ Build service from a line of greppable masscan results """

        # Grab the last column
        service_data = data.split("/")

        self = Service()
        self.port = int(service_data[0])
        self.state = service_data[1]
        self.protocol = service_data[2]
        self.name = service_data[4]
        self.host = None  # data.split("Host: ")[1].split(" ")[0]

        return self

    def json(self) -> Dict[str, Any]:
        """ Converts this object to a dictionary appropriate for JSON output """
        return {
            "port": self.port,
            "protocol": self.protocol,
            "state": self.state,
            "name": self.name,
        }

    @classmethod
    def from_json(cls, data):
        self = Service()
        self.port = data["port"]
        self.protocol = data["protocol"]
        self.state = data["state"]
        self.name = data["name"]
        self.host = None
        return self


@dataclass
class Tracker(object):
    silent: bool
    machine: Any
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

    def match(self, machine: "htb.machine.Machine") -> List[Service]:
        """ Match this scanner to a service. Returns true if it matches """
        return [service for service in machine.services if self.match_service(service)]

    def match_service(self, service: Service) -> bool:
        return service.protocol in self.protocol and (
            service.port in self.ports
            or any([r.match(service.name) for r in self.regex])
        )

    def background(
        self, tracker: Tracker, path: str, hostname: str, machine, service: Service,
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
            tracker.status = status
            if tracker.stop:
                self.cancel(tracker)

        tracker.events.put(tracker)

    def _do_background_scan(
        self, tracker: Tracker, path: str, hostname: str, machine, service: Service,
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
        self, tracker: Tracker, path: str, hostname: str, machine, service: Service,
    ) -> None:
        """ Scan the service on this host """
        yield "running"


class ExternalScanner(Scanner):

    LINE_DELIM = [b"\n"]

    def __init__(self, *args, **kwargs):
        super(ExternalScanner, self).__init__(*args, **kwargs)

    def scan(
        self,
        tracker: Tracker,
        path: str,
        hostname: str,
        machine: "htb.machine.Machine",
        service: Service,
        argv: List[str],
    ):
        """ Start the external application (specified by argv) and monitor output """

        # Call gobuster
        tracker.data["popen"] = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=lambda: signal.signal(signal.SIGTSTP, signal.SIG_IGN),
        )

        line = b""

        # Track start time
        start_time = time.time()

        while tracker.data["popen"].poll() is None:

            # Grab next byte
            data = tracker.data["popen"].stdout.read(1)

            # Not silent, output
            if not tracker.silent:
                sys.stdout.write(data.decode("utf-8"))

            if data in self.LINE_DELIM:

                # Set status
                status = self.do_line(tracker, service, line)
                if status is not None:
                    yield status

                line = b""

                # We don't want a busy loop. Sleep after every line
                if tracker.silent:
                    time.sleep(0.1)
            else:
                line += data

        yield f"completed in {datetime.timedelta(seconds=time.time()-start_time)}"

    def do_line(self, tracker: Tracker, service: Service, line: bytes):
        """ Process a line of output from the subprocess """

        pass

    def cancel(self, tracker: Tracker) -> None:
        """ Ensure the running process dies """

        tracker.data["popen"].terminate()
        try:
            tracker.data["popen"].wait(timeout=1)
        except subprocess.TimeoutExpired:
            tracker.data["popen"].kill()
            tracker.data["popen"].wait()
