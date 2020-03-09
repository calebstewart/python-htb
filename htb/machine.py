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
        self.rating: float = data["rating"]
        self.user_owns: int = data["user_owns"]
        self.root_owns: int = data["root_owns"]
        self.retired: bool = data["retired"]
        self.free: bool = data["free"]

        # May exist
        if "maker2" in data and data["maker2"] is not None:
            self.makers.append(data["maker2"])

        # Other data that might exist depending on machine specifics
        if "todo" in data:
            self._todo: bool = data["todo"]
        else:
            self._todo: bool = False

        if "expires_at" in data:
            self.expires: str = data["expires_at"]
        else:
            self.expires: str = "N/A"

        if "spawned" in data:
            self._spawned: bool = data["spawned"]
        else:
            self._spawned: bool = False

        if "terminating" in data:
            self._terminating: bool = data["terminating"]
        else:
            self._terminating: bool = False

        if "assigned" in data:
            self._assigned: bool = data["assigned"]
        else:
            self._assigned: bool = False

        if "resetting" in data:
            self._resetting: bool = data["resetting"]
        else:
            self._resetting: bool = False

        if "owned_user" in data:
            self.owned_user: bool = data["owned_user"]
        else:
            self.owned_user: bool = False

        if "owned_root" in data:
            self.owned_root: bool = data["owned_root"]
        else:
            self.owned_root: bool = False

        if "difficulty_ratings" in data:
            self.ratings: List[int] = data["difficulty_ratings"]
        else:
            self.ratings: List[int] = [0] * 10

    def __repr__(self) -> str:
        return f"""<Machine name="{self.name}",ip="{self.ip}",spawned={self.spawned}>"""

    @property
    def todo(self) -> bool:
        return self._todo

    @todo.setter
    def todo(self, value: bool) -> None:
        """ Change the current todo status """

        # Don't do anything if it's already right
        if self._todo == value:
            return

        # Attempt to update todo
        r = self.connection._api(f"/machines/todo/update/{self.id}", method="post",)

        # Set todo appropriately
        self._todo = any([x["id"] == self.id and x["todo"] for x in r])

    @property
    def spawned(self) -> bool:
        return self._spawned

    @spawned.setter
    def spawned(self, value: bool) -> None:
        """ Start or stop the machine """

        # No change
        if self.spawned == value:
            return
        elif value:
            action = "assign"
        else:
            action = "remove"

        # Attempt to  start/stop the VM
        r = self.connection._api(f"/vm/vip/{action}/{self.id}", method="post",)

        if r["success"] != 1:
            raise RequestFailed(r["status"])

        # Assign flags based on what we just did
        if action == "remove":
            self._terminating = True
        else:
            self._spawned = True
            self._assigned = True

    @property
    def assigned(self) -> bool:
        return self._assigned

    @assigned.setter
    def assigned(self, value: bool) -> bool:

        # No action
        if self.assigned == value:
            return

        # We don't want to be the owner anymore
        if not value:
            # Trigger setter to remove the VM
            self.spawned = False

        # We want to transfer ownership to ourselves
        r = self.connection._api(f"/vm/vip/assign/{self.id}", method="post",)

        if r["success"] != 1:
            raise RequestFailed(r["status"])

        # The machine now belongs to us
        self._assigned = True

    @property
    def terminating(self) -> bool:
        return self._terminating

    @terminating.setter
    def terminating(self, value: bool) -> None:
        """ Terminate a machine or cancel termination """

        # No change
        if self._terminating == value:
            return

        # Make request
        action = "remove" if value else "cancel"
        r = self.connection._api(f"/vm/vip/{action}/{self.id}", method="post")
        if r["success"] != 1:
            raise RequestFailed(r["status"])

        # Assign value for tracking
        self._terminating = value

    @property
    def resetting(self) -> bool:
        return self._resetting

    @resetting.setter
    def resetting(self, value: bool) -> None:
        """ Reset a machine """

        # No change
        if self._resetting == value:
            return

        # Attempt the reset
        action = "" if value else "cancel/"
        r = self.connection._api(f"/vm/reset/{action}{self.id}", method="post")

        # Raise exception on failure
        if r["success"] != 1:
            raise RequestFailed(r["status"])

        self._resetting = value

    def submit(self, flag: str, difficulty: str = 50):
        """ Submit a flag for this machine """

        r = self.connection._api(
            "/machines/own",
            method="post",
            json={"flag": flag, "difficulty": difficulty, "id": self.id},
        )

        return r["success"] != 0

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
