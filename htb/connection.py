#!/usr/bin/env python3
from typing import Any, Dict, List, Union, Callable
import requests
import time
import re

from htb.exceptions import AuthFailure, TwoFactorAuthRequired
from htb.vpn import VPN
from htb.machine import Machine


class Connection(object):
    """ Server Connection Object """

    BASE_URL = "https://www.hackthebox.eu"

    def __init__(
        self,
        api_token: str,
        email=None,
        password=None,
        twofactor_prompt: Callable = None,
    ):
        """ Construct a connection with the specified API key """

        # Save the API key
        self.api_token: str = api_token

        # Save authentication information, if we were given any
        self.email: str = email
        self.password: str = password

        # API result cache
        self._cache: Dict[str, Any] = {}
        self.cache_timeout: float = 60

        # Callback to get two factor prompt
        self.twofactor_prompt = twofactor_prompt

        # Ongoing session for standard authentication
        self.session = requests.Session()

    def invalidate_cache(self, endpoint: str = None, method: str = None) -> None:
        """ Invalidate the cache of one endpoint, endpoint/method or all entries """

        if endpoint is None:
            self._cache = {}
        elif method is None and endpoint in self._cache:
            self._cache[endpoint] = {}
        elif endpoint in self._cache and method in self._cache[endpoint]:
            self._cache[endpoint][method] = (0, None)

    def _api(self, endpoint, args={}, method="post", cache=False, **kwargs) -> Dict:
        """ Send an API requests with the stored API key """

        # If requested, attempt to cache the response for up to `self.cache_timeout` seconds
        if cache and endpoint in self._cache and method in self._cache[endpoint]:
            if (time.time() - self._cache[endpoint][method][0]) < self.cache_timeout:
                return self._cache[endpoint][method][1]

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

        # Save the response for future cache reuse
        if cache:
            if endpoint not in self._cache:
                self._cache[endpoint] = {}
            self._cache[endpoint][method] = (time.time(), response)

        return response

    def _request(
        self, endpoint, method, _retry_auth=True, **kwargs
    ) -> requests.Response:
        """ Make a standard (non-api) request. May require authentication prior,
        but in order to authenticate, the connection must have been given
        credentials beyond the required auth token. """

        # Easy lookup table for request method
        methods = {"get": self.session.get, "post": self.session.post}
        headers = {"User-Agent": "https://github.com/calebstewart/python-htb"}

        if "headers" in kwargs:
            kwargs["headers"].update(headers)
        else:
            kwargs["headers"] = headers

        # Send request
        r = methods[method](
            f"{Connection.BASE_URL}/{endpoint.lstrip('/')}",
            allow_redirects=False,
            **kwargs,
        )

        if r.status_code == 302:
            if _retry_auth:
                self._authenticate()
                return self._request(endpoint, method, _retry_auth=False, **kwargs)
            else:
                raise AuthFailure

        return r

    def _authenticate(self) -> None:
        """ Check that the provided API key is valid and query user details """

        # Attempt to grab connection status
        r = self._api("/users/htb/connection/status")

        # Test email/password auth as well
        if self.email is not None and self.password is not None:

            # Build session object
            self.session = requests.Session()
            headers = {"User-Agent": "https://github.com/calebstewart/python-htb"}

            # Grab CSRF Token
            r = self.session.get(f"{Connection.BASE_URL}/login", headers=headers)
            data = r.text.split('id="loginForm"')[1]
            token = data.split('_token" value="')[1].split('"')[0]

            # Authenticate
            r = self.session.post(
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

            # Check for Two Factor Authentication
            r = self.session.get(r.headers["location"], headers=headers)
            if "One Time Password" not in r.text:
                return

            # Prompt for the one time password
            token = (
                r.text.split('id="loginForm"')[1]
                .split('_token" value="')[1]
                .split('"')[0]
            )

            # Request the two-factor one time passcode
            otp = self.twofactor_prompt()

            r = self.session.post(
                f"{Connection.BASE_URL}/2fa",
                data={"_token": token, "one_time_password": otp, "backup_code": ""},
                allow_redirects=False,
                headers=headers,
            )
            if (
                r.status_code != 302
                or r.headers["location"] != "https://www.hackthebox.eu/home"
            ):
                raise TwoFactorAuthRequired

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
        machines = self._api("/machines/get/all", method="get", cache=True)

        # Create machine objects for all the machine information
        return [Machine(self, m) for m in machines]

    def get_machine(self, ident: int) -> Machine:
        """ Lookup a machine by ID """

        # request the machine
        machine = self._api(f"/machines/get/{ident}", method="get", cache=True)

        return Machine(self, machine)

    @property
    def active(self) -> List[Machine]:
        """ Grab all active machines """
        return [m for m in self.machines if not m.retired]

    @property
    def retired(self) -> List[Machine]:
        """ Grab all retired machines """
        return [m for m in self.machines if m.retired]

    @property
    def todo(self) -> List[Machine]:
        """ List of machines marked as "todo" """
        return [m for m in self.machines if m.todo]

    @property
    def assigned(self) -> Machine:
        """ Return the machine assigned to your or None """
        for m in self.machines:
            if m.assigned:
                return m
        return None

    @property
    def spawned(self) -> List[Machine]:
        """ All spawned/running machines """
        return [m for m in self.machines if m.spawned]

    def shout(self, message) -> None:
        """ Send a message on the shoutbox """
        r = self._api("/shouts/new/", data={"text": message})
        return r

    def __getitem__(self, value: Union[str, int]):
        """ Lookup a machine based on either its integer ID or a regular
        expression matching its name or IP address """

        # Find the machine based on name regex
        if isinstance(value, str):
            m = [
                m
                for m in self.machines
                if re.match(value, m.name, flags=re.IGNORECASE)
                or re.match(value, m.ip, flags=re.IGNORECASE)
            ]
        # Find machine based on ID
        elif isinstance(value, int):
            m = [self.get_machine(value)]
        else:
            # Invalid search
            raise ValueError("expected machine id or name regex")

        # Machine does not exist
        if len(m) == 0:
            raise KeyError("no matching machine found")

        # Return first match
        return m[0]
