#!/usr/bin/env python3
from typing import Dict, Any, List

from htb.exceptions import RequestFailed


class Machine(object):
    """ Interact with a Hack the Box machine """

    def __init__(self, connection: Any, data: Dict[str, Any]):
        """ Build a machine object from API data """

        self.connection = connection

        # Standard data (should always exist)
        self.id: int = data["id"]
        self.name: str = data["name"]
        self.os: str = data["os"]
        self.ip: str = data["ip"]
        self.avatar: str = data["avatar_thumb"]
        self.points: str = data["points"]
        self.release_date: str = data["release"]
        self.retire_date: str = data["retired_date"]
        self.makers: List[Dict] = [data["maker"]]
        # self.rating: float = float(data["rating"])
        self.rating: float = 0.0
        self.user_owns: int = data["user_owns"]
        self.root_owns: int = data["root_owns"]
        # self.retired: bool = data["retired"]
        # self.free: bool = data["free"]
        self.free: bool = False

        # May exist
        if "maker2" in data and data["maker2"] is not None:
            self.makers.append(data["maker2"])

    def __repr__(self) -> str:
        return f"""<Machine id={self.id},name="{self.name}",ip="{self.ip}",os="{self.os}">"""

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
            return None

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
        r = self.connection._api(f"/machines/todo/update/{self.id}", method="post",)

    @spawned.setter
    def spawned(self, value: bool) -> None:
        """ Start or stop the machine """

        if value:
            action = "assign"
        else:
            action = "remove"

        # Attempt to  start/stop the VM
        r = self.connection._api(f"/vm/vip/{action}/{self.id}", method="post",)

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
        r = self.connection._api(f"/vm/vip/assign/{self.id}", method="post",)

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
            json={"flag": flag, "difficulty": difficulty, "id": self.id},
        )

        return int(r["success"]) != 0

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
