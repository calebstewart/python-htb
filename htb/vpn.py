#!/usr/bin/env python3
from typing import Any, Dict, List

from htb.exceptions import RequestFailed


class VPN(object):
    """ Represents the VPN server you're currently attached to """

    US_FREE = "usfree"
    US_VIP = "usvip"
    EU_FREE = "eufree"
    EU_VIP = "euvip"
    AU_FREE = "aufree"
    VALID_LABS = [US_FREE, US_VIP, EU_FREE, EU_VIP, AU_FREE]

    def __init__(self, connection: Any, data: Dict[str, Any]):
        """ Create a new VPN object from status information """

        # Certain data is only available when connected
        if data["success"] == 0:
            self.ipv4: str = None
            self.ipv6: str = None
            self.rate_up: float = 0
            self.rate_down: float = 0
            self.user: str = None
            self.active: bool = False
        else:
            self.active: bool = True
            self.user: str = data["name"]
            self.ipv4: str = data["ip4"]
            self.ipv6: str = data["ip6"]
            self.rate_up: float = data["up"]
            self.rate_down: float = data["down"]

        # Server information is always available
        self.hostname = data["server"]["serverHostname"]
        self.port = data["server"]["serverPort"]
        self.connection = connection

    def switch(self, lab: str) -> None:
        """ Switch to a different lab. **NOTE** regenerates keys! """

        if "-fort-" in self.hostname:
            raise ValueError("Fortress labs cannot be switched")

        if lab not in VPN.VALID_LABS:
            raise ValueError(f"unknown lab name: {lab}")

        r = self.connection._api(f"/labs/switch/{lab}", method="post")
        if int(r["status"]) != 1:
            raise RequestFailed(r["error"])

    @property
    def config(self) -> bytes:
        """ Get the ovpn configuration. This is only possible if you provided
        Hack the Box username and password. """

        r = self.connection._request(f"/home/htb/access/ovpnfile", method="get")
        if r.status_code != 200:
            raise RequestFailed("unknown error")

        return bytes(r.text, "utf-8")

    def __repr__(self) -> str:
        if self.active:
            return f"""<VPN ipv4="{self.ipv4}", up={self.rate_up}, down={self.rate_down}, server="{self.hostname}:{self.port}">"""
        else:
            return f"""<VPN active=False, server="{self.hostname}:{self.port}">"""
