#!/usr/bin/env python3
from typing import Any, Dict, List
import requests

from htb.exceptions import AuthFailure
from htb.vpn import VPN
from htb.machine import Machine


class Connection(object):
    """ Server Connection Object """

    BASE_URL = "https://www.hackthebox.eu"

    def __init__(self, api_token: str, email=None, password=None):
        """ Construct a connection with the specified API key """

        # Save the API key
        self.api_token: str = api_token

        # Save authentication information, if we were given any
        self.email: str = email
        self.password: str = password

        # Ensure we can authenticate with this api key
        self._authenticate()

    def _api(self, endpoint, args={}, method="post", **kwargs) -> Dict:
        """ Send an API requests with the stored API key """

        # Construct necessary parameters for request
        url = f"{Connection.BASE_URL}/api/{endpoint.lstrip('/')}"
        headers = {
            "User-Agent": "https://github.com/calebstewart/python-htb",
            "Authorization": f"Bearer {self.api_token}",
        }
        methods = {"post": requests.post, "get": requests.get}
        args.update({"api_token": self.api_token})

        # Request failed
        r = methods[method.lower()](
            url, params=args, headers=headers, allow_redirects=False, **kwargs
        )
        if r.status_code != 200:
            raise AuthFailure

        # Grab response data
        response = r.json()

        # It's an integer but they always send it as a string :(
        if "success" in response:
            if isinstance(response["success"], str):
                response["success"] = int(response["success"])

        return response

    def _request(self, endpoint, method, auth=True, **kwargs) -> requests.Response:
        """ Make a standard (non-api) request. May require authentication prior,
        but in order to authenticate, the connection must have been given
        credentials beyond the required auth token. """

        # If we are going to authenticate, we need to track our session
        if auth:
            s = requests.Session()
        else:
            s = requests

        # Easy lookup table for request method
        methods = {"get": s.get, "post": s.post}
        headers = {"User-Agent": "https://github.com/calebstewart/python-htb"}

        if auth:

            if self.email is None or self.password is None:
                raise AuthError("No credentials provided")

            # Grab CSRF Token
            r = s.get(f"{Connection.BASE_URL}/login", headers=headers)
            data = r.text.split('id="loginForm"')[1]
            token = data.split('_token" value="')[1].split('"')[0]

            # Authenticate
            r = s.post(
                f"{Connection.BASE_URL}/login",
                data={"_token": token, "email": self.email, "password": self.password},
                allow_redirects=False,
                headers=headers,
            )

            # Ensure we succeeded
            if (
                r.status_code != 302
                or r.headers["location"] != "https://www.hackthebox.eu/home"
            ):
                raise AuthFailure

        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers

        # Send request
        return methods[method](
            f"{Connection.BASE_URL}/{endpoint.lstrip('/')}", **kwargs
        )

    def _authenticate(self) -> None:
        """ Check that the provided API key is valid and query user details """

        # Attempt to grab connection status
        r = self._api("/users/htb/connection/status")

        # Test email/password auth as well
        if self.email is not None and self.password is not None:
            r = self._request("/home", method="get")

    def switch_vpn(self, vpn) -> None:
        """ Switch to the specified VPN region """

        pass

    @property
    def lab(self) -> VPN:
        """ Grab the Lab VPN object """
        r = self._api("/users/htb/connection/status")
        return VPN(self, r)

    @property
    def fortress(self) -> VPN:
        """ Grab the Fortress VPN object """
        r = self._api("/users/htb/fortress/connection/status")
        return VPN(self, r)

    @property
    def machines(self) -> List[Machine]:
        """ Grab the list of active machines """

        # Request all the machine information
        machines = self._api("/machines/get/all", method="get")
        owns = self._api("/machines/owns", method="get")
        difficulties = self._api("/machines/difficulty", method="get")
        reviews = self._api("/machines/reviews", method="get")
        todos = self._api("/machines/todo", method="get")
        expiry = self._api("/machines/expiry", method="get")
        spawned = self._api("/machines/spawned", method="get")
        terminating = self._api("/machines/terminating", method="get")
        assigned = self._api("/machines/assigned", method="get")
        resetting = self._api("/machines/resetting", method="get")

        # Create dictionary mapping machine ID to machine description
        machines = {machine["id"]: machine for machine in machines}

        # Add all the extra data to the machine dictionaries
        for x in [
            owns,
            difficulties,
            reviews,
            todos,
            expiry,
            spawned,
            terminating,
            assigned,
            resetting,
        ]:
            for y in x:
                if isinstance(y, dict):
                    if y["id"] in machines:
                        machines[y["id"]].update(y)

        # Create machine objects for all the machine information
        return [Machine(self, m) for ident, m in machines.items()]

    @property
    def active(self) -> List[Machine]:
        return [m for m in self.machines if not m.retired]

    @property
    def retired(self) -> List[Machine]:
        return [m for m in self.machines if m.retired]

    @property
    def todo(self) -> List[Machine]:
        return [m for m in self.machines if m.todo]

    @property
    def assigned(self) -> Machine:
        for m in self.machines:
            if m.assigned:
                return m
        return None

    @property
    def spawned(self) -> List[Machine]:
        return [m for m in self.machines if m.spawned]
