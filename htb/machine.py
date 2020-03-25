#!/usr/bin/env python3
from typing import Dict, Any, List
from io import StringIO
import subprocess
import threading
import json
import os
import re

from htb.scanner import Service, Scanner, Tracker, AVAILABLE_SCANNERS
from htb.exceptions import *


class Machine(object):
    """ Interact with a Hack the Box machine """
    
    def __init__(self, connection: Any, data: Dict[str, Any]):
        """ Build a machine object from API data """
        
        self.connection = connection
        
        # Standard data (should always exist)
        self.id: int = None
        self.name: str = None
        self.os: str = None
        self.ip: str = None
        self.avatar: str = None
        self.points: str = None
        self.release_date: str = None
        self.retire_date: str = None
        self.makers: List[Dict] = None
        self.rating: float = None
        self.user_owns: int = None
        self.root_owns: int = None
        self.free: bool = None
        self.analysis_path: str = None
        self.services: List[Service] = []
        self.knowns: Dict[str, Any] = {}
        
        self.update(data)
    
    def __repr__(self) -> str:
        return f"""<Machine id={self.id},name="{self.name}",ip="{self.ip}",os="{self.os}">"""
    
    def update(self, data: Dict[str, Any]):
        """ Update internal machine state from recent request """
        
        # Standard data (should always exist)
        self.id: int = data["id"]
        self.name: str = data["name"].lower()  # We don't like capitals :(
        self.os: str = data["os"]
        self.ip: str = data["ip"]
        self.avatar: str = data["avatar_thumb"]
        self.points: str = data["points"]
        self.release_date: str = data["release"]
        self.retire_date: str = data["retired_date"]
        self.makers: List[Dict] = [data["maker"]]
        self.rating: float = 0.0
        self.user_owns: int = data["user_owns"]
        self.root_owns: int = data["root_owns"]
        self.free: bool = False
        
        # May exist
        if "maker2" in data and data["maker2"] is not None:
            self.makers.append(data["maker2"])
    
    @property
    def hostname(self) -> str:
        return f"{self.name.lower()}.htb"
    
    @property
    def todo(self) -> bool:
        """ Whether this machine on the todo list """
        todos = self.connection._api("/machines/todo", method="get", cache=True)
        return any([t["id"] == self.id for t in todos])
    
    @property
    def expires(self) -> str:
        """ The time until this machine expires """
        
        # Grab expiration information for all machines
        expiry = self.connection._api("/machines/expiry", method="get", cache=True)
        
        try:
            # Return the expire time for this machine
            return [t["expires_at"] for t in expiry if t["id"] == self.id][0]
        except IndexError:
            # Or return none if it is not running/has no expiration time
            return None
    
    @property
    def spawned(self) -> bool:
        """ Whether this machine has been spawned """
        
        spawned = self.connection._api("/machines/spawned", method="get", cache=True)
        
        return any([s["id"] == self.id for s in spawned])
    
    @property
    def terminating(self) -> bool:
        """ Whether this machine has been spawned """
        
        terminating = self.connection._api(
            "/machines/terminating", method="get", cache=True
        )
        
        return any([s["id"] == self.id for s in terminating])
    
    @property
    def assigned(self) -> bool:
        """ Whether this machine is currently assigned to the logged in user """
        
        machines = self.connection._api("/machines/assigned", method="get", cache=True)
        
        return any([m["id"] == self.id for m in machines])
    
    @property
    def retired(self) -> bool:
        """ Whether this machine is currently assigned to the logged in user """
        
        machines = self.connection._api("/machines/get/all", method="get", cache=True)
        
        try:
            return [m["retired"] for m in machines if m["id"] == self.id][0]
        except IndexError:
            return False
    
    @property
    def resetting(self) -> bool:
        """ Whether this machine has been requested to reset """
        
        machines = self.connection._api("/machines/resetting", method="get", cache=True)
        
        return any([m["id"] == self.id for m in machines])
    
    @property
    def owned_user(self) -> bool:
        """ Whether you have owned user on this machine """
        
        machines = self.connection._api("/machines/owns", method="get", cache=True)
        
        return any([m["id"] == self.id and m["owned_user"] for m in machines])
    
    @property
    def owned_root(self) -> bool:
        """ Whether you have owned root on this machine """
        
        machines = self.connection._api("/machines/owns", method="get", cache=True)
        
        return any([m["id"] == self.id and m["owned_root"] for m in machines])
    
    @property
    def ratings(self) -> bool:
        """ The difficulty rating for this machine """
        
        machines = self.connection._api(
            "/machines/difficulty", method="get", cache=True
        )
        
        try:
            return [m["difficulty_ratings"] for m in machines if m["id"] == self.id][0]
        except IndexError:
            return [0 for i in range(10)]
    
    @property
    def matrix(self) -> Dict[str, List[int]]:
        """ Get the rating matrix for this machine """
        r = self.connection._api(
            f"/machines/get/matrix/{self.id}", method="get", cache=True
        )
        if r["success"] != 1:
            return {"aggregate": [0] * 5, "maker": [0] * 5}
        
        return {"aggregate": r["aggregate"], "maker": r["maker"]}
    
    @property
    def blood(self) -> Dict[str, str]:
        """ Grab machine blood information """
        r = self.connection._api(f"/machines/get/{self.id}", method="get", cache=True)
        return {"user": r["user_blood"], "root": r["root_blood"]}
    
    @todo.setter
    def todo(self, value: bool) -> None:
        """ Change the current todo status """
        
        # Don't do anything if it's already right
        if self.todo == value:
            return
        
        # Attempt to update todo
        r = self.connection._api(f"/machines/todo/update/{self.id}", method="post", )
    
    @spawned.setter
    def spawned(self, value: bool) -> None:
        """ Start or stop the machine """
        
        if value:
            action = "assign"
        else:
            action = "remove"
        
        # Attempt to  start/stop the VM
        r = self.connection._api(f"/vm/vip/{action}/{self.id}", method="post", )
        
        if r["success"] != 1:
            raise RequestFailed(r["status"])
    
    @assigned.setter
    def assigned(self, value: bool) -> bool:
        
        # We don't want to be the owner anymore
        if not value:
            # Trigger setter to remove the VM
            self.spawned = False
            return
        
        # We want to transfer ownership to ourselves
        r = self.connection._api(f"/vm/vip/assign/{self.id}", method="post", )
        
        if r["success"] != 1:
            raise RequestFailed(r["status"])
    
    @terminating.setter
    def terminating(self, value: bool) -> None:
        """ Terminate a machine or cancel termination """
        
        # Make request
        action = "remove" if value else "cancel"
        r = self.connection._api(f"/vm/vip/{action}/{self.id}", method="post")
        if r["success"] != 1:
            raise RequestFailed(r["status"])
    
    @resetting.setter
    def resetting(self, value: bool) -> None:
        """ Reset a machine """
        
        # Attempt the reset
        action = "/vm/reset" if value else "/machines/reset/cancel"
        r = self.connection._api(f"{action}/{self.id}", method="post")
        
        # Raise exception on failure
        if r["success"] != 1:
            raise RequestFailed(r["status"])
    
    def submit(self, flag: str, difficulty: str = 50):
        """ Submit a flag for this machine """
        
        r = self.connection._api(
            "/machines/own",
            method="post",
            json={"flag": flag, "difficulty": int(difficulty), "id": self.id},
        )
        
        if r["success"] == 0:
            raise RequestFailed(r["status"])
        
        return True
    
    def extend(self) -> bool:
        """ Extend machine uptime """
        
        # Machine isn't up
        if not self.spawned:
            return False
        
        # https://www.hackthebox.eu/api/vm/vip/extend/213
        r = self.connection._api(f"/vm/vip/extend/{self.id}", method="post")
        if r["success"] != 1:
            return RequestFailed(r["status"])
        
        return True
    
    def review(self, stars: int, message: str) -> None:
        """ Submit a review for a machine """
        
        r = self.connection._api(
            f"/machines/review",
            method="post",
            json={"stars": stars, "message": message},
        )
    
    def init(self, base_path="./") -> None:
        """ Initialize analysis directory and load an previous enumerations """
        
        # Check if we already initialized the directory tree
        try:
            self.load(base_path)
        except NoAnalysisPath:
            # We didn't, pass to this function to do initialization
            pass
        else:
            # We did, our job is done
            return
        
        # Create analysis path and check if it's currently a file
        self.analysis_path = os.path.abspath(
            os.path.expanduser(os.path.join(base_path, self.name.lower()))
        )
        
        # Create analysis structure
        os.makedirs(os.path.join(self.analysis_path, "scans"), exist_ok=True)
        os.makedirs(os.path.join(self.analysis_path, "artifacts"), exist_ok=True)
        os.makedirs(os.path.join(self.analysis_path, "exploits"), exist_ok=True)
        os.makedirs(os.path.join(self.analysis_path, "img"), exist_ok=True)
        
        # Create initial readme
        with open(os.path.join(self.analysis_path, "README.md"), "w") as f:
            f.write(f"# Hack the Box - {self.name} - {self.ip}\n")
        
        # Build hostname
        hostname = f"{self.name.lower()}.htb"
        
        # Check if we are already in /etc/hosts
        with open("/etc/hosts", "r") as f:
            in_hosts = any(
                [
                    re.fullmatch(f"^{self.ip}.*\\s+{self.hostname}.*$", line)
                    is not None
                    for line in f
                ]
            )
        
        # Add our host to /etc/hosts if needed
        if not in_hosts:
            code = subprocess.run(
                ["sudo", "tee", "-a", "/etc/hosts"],
                input=bytes(f"\n{self.ip}\t{hostname}", "utf-8"),
                stdout=subprocess.DEVNULL,
            )
            if code.returncode != 0:
                raise EtcHostsFailed
    
    def dump(self) -> bool:
        """ Dump our current findings and services to a state file in the
        anaylsis directory. If this machine has not been initialized, then don't
        do anything. """
        
        if self.analysis_path is None:
            return False
        
        with open(os.path.join(self.analysis_path, "machine.json"), "w") as fh:
            json.dump(
                {"services": [s.json() for s in self.services], "knowns": self.knowns},
                fh,
            )
        
        return True
    
    def load(self, base_path: str = "./") -> None:
        """ Load saved machine information from `machine.json` in the analysis
        directory. """
        
        # Ensure the directory exists
        analysis_path = os.path.expanduser(
            os.path.join(base_path, f"{self.name.lower()}")
        )
        if not os.path.isdir(analysis_path):
            raise NoAnalysisPath
        
        try:
            with open(os.path.join(analysis_path, "machine.json"), "r") as fh:
                data = json.load(fh)
                self.services = [Service.from_json(s) for s in data["services"]]
                self.knowns = data["knowns"]
            self.analysis_path = analysis_path
        except OSError as e:
            # No machine.json file
            print(f"oserror: {e}")
            raise NoAnalysisPath
        except KeyError as e:
            print(f"keyerror: {e}")
            # Invalid machine json format
            raise NoAnalysisPath
    
    def enumerate(self, force: bool = False) -> None:
        """ Enumerate running services on the machine

        :param force: Force enumeration if it is already completed
        :type force: bool
        """
        
        # The machine has to be running
        if not self.spawned:
            raise NotRunning
        
        # It also needs to not be actively terminating
        if self.terminating:
            raise Terminating
        
        # We already enumerated this machine
        if not force and len(self.services):
            return
        
        masscan_path = os.path.join(self.analysis_path, "scans", "masscan.grep")
        code = subprocess.call(
            [
                "sudo",
                "masscan",
                self.ip,
                "-p",
                "1-65535",
                "--max-rate",
                "1000",
                "-oG",
                masscan_path,
                "-e",
                "tun0",
            ]
        )
        
        # Ensure masscan succeeded
        if code != 0:
            raise MasscanFailed
        
        # Read all open port lines
        with open(masscan_path, "r") as f:
            ports = [
                int(line.split(" ")[-1].split("/")[0])
                for line in f.read().split("\n")
                if line != "" and line[0] != "#" and "open" in line
            ]
        
        # Run an in-depth nmap scan for the open ports
        nmap_path = os.path.join(self.analysis_path, "scans", "open-tcp")
        code = subprocess.call(
            [
                "nmap",
                "-Pn",
                "-T5",
                "-sV",
                "-A",
                "-p",
                ",".join([str(p) for p in ports]),
                "-oA",
                nmap_path,
                self.hostname,
            ]
        )
        
        # Check nmap result
        if code != 0:
            raise NmapFailed
        
        # Read greppable nmap output and extract open services
        with open(nmap_path + ".gnmap", "r") as f:
            services_list = [
                line.split("Ports: ")[1]
                for line in f.read().split("\n")
                if line != "" and line[0] != "#" and "Ports:" in line
            ]
        
        self.services = []
        for l in services_list:
            for s in l.split("/, "):
                self.services.append(Service.from_nmap((s + "/").strip()))
        
        # Ensure we write the services out
        self.dump()
    
    def scan(self, scanner: Scanner, service: Service, silent=False) -> Tracker:
        """ Start a scan for the given service. A tracker is allocated with the
        lock held and the `job_events` field set to None. """
        
        if not scanner.match_service(service):
            raise NotApplicable
        
        # Construct a tracker object
        tracker = Tracker(
            silent=silent,
            machine=self,
            service=service,
            scanner=scanner,
            status="",
            events=None,
            thread=None,
            stop=False,
            data={},
            lock=threading.Lock(),
        )
        
        # Acquire the lock so the scanner doesn't modify the event queue before
        # initialization
        tracker.lock.acquire()
        
        # Start the background scan
        tracker.thread = scanner.background(
            tracker, self.analysis_path, self.hostname, self, service
        )
        
        return tracker
