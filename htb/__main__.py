#!/usr/bin/env python3
from typing import Any
import cmd2
from cmd2 import Cmd
from cmd2.argparse_custom import Cmd2ArgumentParser
import configparser
import NetworkManager
import subprocess
from colorama import Fore, Style, Back
import argparse
import os.path
import tempfile
import shlex
import time
import dbus
import sys
import os

from htb import Connection, Machine, VPN
from htb.exceptions import (
    RequestFailed,
    AuthFailure,
    ConnectionNotFound,
    InvalidConnectionID,
)
import htb.scanner


class HackTheBox(Cmd):
    """ Hack the Box Command Line Interface """

    OS_ICONS = {
        "freebsd": "\uf3a4",
        "windows": "\uf17a",
        "linux": "\uf17c",
        "android": "\uf17b",
        "solaris": "\uf185",
        "other": "\uf233",
    }

    def __init__(self, resource="~/.htbrc", *args, **kwargs):
        super(HackTheBox, self).__init__(*args, **kwargs)

        # Find file location referencing "~"
        path_resource = os.path.expanduser(resource)
        if not os.path.isfile(path_resource):
            raise RuntimeError(f"{resource}: no such file or directory")

        # Read configuration
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path_resource)

        # Save the configuration for later
        self.config_path: str = path_resource
        self.config = parser

        # Extract relevant information
        email = parser["htb"].get("email", None)
        password = parser["htb"].get("password", None)
        api_token = parser["htb"].get("api_token", None)

        # Ensure we have an API token
        if api_token is None:
            raise RuntimeError("no api token provided!")

        # Construct the connection object
        self.cnxn: Connection = Connection(
            api_token=api_token, email=email, password=password
        )

        self.prompt = (
            f"{Fore.CYAN}htb{Fore.RESET} {Style.BRIGHT+Fore.GREEN}➜{Style.RESET_ALL} "
        )

    def poutput(self, msg: Any = "", end: str = "\n", apply_style: bool = True) -> None:
        if apply_style:
            msg = f"[{Style.BRIGHT+Fore.BLUE}-{Style.RESET_ALL}] {msg}"
        super(HackTheBox, self).poutput(msg, end=end)

    def psuccess(
        self, msg: Any = "", end: str = "\n", apply_style: bool = True
    ) -> None:
        if apply_style:
            msg = f"[{Style.BRIGHT+Fore.GREEN}+{Style.RESET_ALL}] {msg}"
        super(HackTheBox, self).poutput(msg, end=end)

    def pwarning(
        self, msg: Any = "", end: str = "\n", apply_style: bool = True
    ) -> None:
        if apply_style:
            msg = f"[{Style.BRIGHT+Fore.YELLOW}?{Style.RESET_ALL}] {msg}"
        super(HackTheBox, self).pwarning(
            msg, end=end, apply_style=False,
        )

    def perror(self, msg: Any = "", end: str = "\n", apply_style: bool = True) -> None:
        if apply_style:
            msg = f"[{Style.BRIGHT+Fore.RED}!{Style.RESET_ALL}] {msg}"
        super(HackTheBox, self).perror(
            msg, end=end, apply_style=False,
        )

    # Argument parser for `machine` command
    machine_parser = Cmd2ArgumentParser(
        description="View and manage active and retired machines"
    )
    machine_parser.set_defaults(action="list")
    machine_subparsers = machine_parser.add_subparsers(
        help="Actions", required=False, dest="_action"
    )

    @cmd2.with_argparser(machine_parser)
    @cmd2.with_category("Hack the Box")
    def do_machine(self, args: argparse.Namespace) -> bool:
        """ View and manage active and retired machines """
        actions = {
            "list": self._machine_list,
            "start": self._machine_start,
            "stop": self._machine_stop,
            "own": self._machine_own,
            "info": self._machine_info,
            "cancel": self._machine_cancel,
            "reset": self._machine_reset,
            "init": self._machine_init,
        }
        actions[args.action](args)
        return False

    machine_list_parser = machine_subparsers.add_parser(
        "list", aliases=["ls"], help="List machines", prog="machine list"
    )
    machine_list_parser.set_defaults(action="list")
    machine_list_parser.add_argument(
        "--inactive", "-i", action="store_const", const="inactive", dest="state"
    )
    machine_list_parser.add_argument(
        "--active",
        "-a",
        action="store_const",
        const="active",
        dest="state",
        default="all",
    )
    machine_list_parser.add_argument(
        "--owned", "-o", action="store_const", const="owned", default="all"
    )
    machine_list_parser.add_argument(
        "--unowned", "-u", action="store_const", const="unowned", dest="owned"
    )
    machine_list_parser.add_argument("--todo", "-t", action="store_true")
    machine_list_parser.set_defaults(state="all", owned="all")

    def _machine_list(self, args: argparse.Namespace) -> None:
        """ List machines on hack the box """

        # Grab all machines
        machines = self.cnxn.machines

        if args.state != "all":
            machines = [m for m in machines if m.retired == (args.state != "active")]
        if args.owned != "all":
            machines = [
                m
                for m in machines
                if (m.owned_root and m.owned_user) == (args.owned == "owned")
            ]
        if args.todo:
            machines = [m for m in machines if m.todo]

        # Pre-calculate column widths to output correctly formatted header
        name_width = max([len(m.name) for m in machines]) + 2
        ip_width = max([len(m.ip) for m in machines]) + 2
        id_width = max([len(str(m.id)) for m in machines]) + 1
        diff_width = 12
        rating_width = 5
        owned_width = 7
        state_width = 13

        # Lookup tables for creating the difficulty ratings
        rating_char = [
            "\u2581",
            "\u2582",
            "\u2583",
            "\u2584",
            "\u2585",
            "\u2586",
            "\u2587",
            "\u2588",
        ]
        rating_color = [*([Fore.GREEN] * 3), *([Fore.YELLOW] * 4), *([Fore.RED] * 3)]

        # Header row
        output = [
            f"{Style.BRIGHT}{' '*id_width}  {'Name':<{name_width}}{'Address':<{ip_width}}{' Difficulty':<{diff_width}}{'Rate':<{rating_width}}{'Owned':<{owned_width}}{'State':<{state_width}}{Style.RESET_ALL}"
        ]

        # Create the individual machine rows
        for m in machines:
            style = Style.DIM if m.owned_user and m.owned_root else ""

            # Create scaled difficulty rating. Highest rated is full. Everything
            # else is scaled appropriately.
            max_ratings = max(m.ratings)
            ratings = [float(r) / max_ratings for r in m.ratings]
            difficulty = ""
            for i, r in enumerate(ratings):
                difficulty += rating_color[i] + rating_char[round(r * 6)]
            difficulty += Style.RESET_ALL

            # "$" for user and "#" for root
            owned = f" {'$' if m.owned_user else ' '} {'#' if m.owned_root else ' '} "

            # Display time left/terminating/resetting/off etc
            if m.spawned and not m.terminating and not m.resetting:
                state = m.expires
            elif m.terminating:
                state = "terminating"
            elif m.resetting:
                state = "resetting"
            else:
                state = "off"

            # Show an astrics and highlight state in blue for assigned machine
            if m.assigned:
                state = Fore.BLUE + state + Style.RESET_ALL
                assigned = f"{Fore.BLUE}*{Style.RESET_ALL} "
            else:
                assigned = "  "

            # Construct row
            output.append(
                f"{style}{m.id:<{id_width}}{assigned}{m.name:<{name_width}}{m.ip:<{ip_width}} {difficulty} {m.rating:<{rating_width}.1f}{owned:<{owned_width}}{state:<{state_width}}{Style.RESET_ALL}"
            )

        # print data
        self.ppaged("\n".join(output))

    machine_start_parser = machine_subparsers.add_parser(
        "start", aliases=["up", "spawn"], help="Start a machine", prog="machine up"
    )
    machine_start_parser.add_argument(
        "machine", help="A name regex, IP address or machine ID to start"
    )
    machine_start_parser.set_defaults(action="start")

    def _machine_start(self, args: argparse.Namespace):
        """ Start a machine """

        # Convert to integer, if possible. Otherwise pass as-is
        try:
            machine_id = int(args.machine)
        except:
            machine_id = args.machine

        m = self.cnxn[machine_id]
        a = self.cnxn.assigned

        if a is not None and a.name != m.name:
            self.perror(f"{a.name} already assigned to you")
            return

        if m is None:
            self.perror(f"{machine_id}: no such machine")
            return

        if m.spawned:
            self.poutput(f"{m.name}: already running. did you mean 'transfer'?")
            return

        self.psuccess(f"starting {m.name}")
        m.spawned = True

    machine_reset_parser = machine_subparsers.add_parser(
        "reset",
        aliases=["restart"],
        help="Schedule a machine reset",
        prog="machine reset",
    )
    machine_reset_parser.add_argument(
        "machine", help="A name regex, IP address or machine ID"
    )
    machine_reset_parser.set_defaults(action="reset")

    def _machine_reset(self, args: argparse.Namespace) -> None:
        """ Stop an active machine """

        # Convert to integer, if possible. Otherwise pass as-is
        try:
            machine_id = int(args.machine)
        except:
            machine_id = args.machine

        m = self.cnxn[machine_id]
        if m is None:
            self.perror(f"{machine_id}: no such machine")
            return

        if not m.spawned:
            self.poutput(f"{m.name}: not running")
            return

        self.success(f"{m.name}: scheduling reset")
        m.resetting = True

    machine_stop_parser = machine_subparsers.add_parser(
        "stop", aliases=["down", "shutdown"], help="Stop a machine", prog="machine down"
    )
    machine_stop_group = machine_stop_parser.add_mutually_exclusive_group(required=True)
    machine_stop_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_stop_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID to start",
    )
    machine_stop_parser.set_defaults(action="stop")

    def _machine_stop(self, args: argparse.Namespace) -> None:
        """ Stop an active machine """

        if args.assigned:
            m = self.cnxn.assigned
            if m is None:
                self.perror(f"no currently assigned machine")
                return
        else:
            # Convert to integer, if possible. Otherwise pass as-is
            try:
                machine_id = int(args.machine)
            except:
                machine_id = args.machine

            try:
                m = self.cnxn[machine_id]
            except KeyError:
                self.perror(f"{machine_id}: no such machine")
                return

        if not m.spawned:
            self.poutput(f"{m.name} is not running")
            return

        self.psuccess(f"scheduling termination for {m.name}")
        m.spawned = False

    machine_info_parser = machine_subparsers.add_parser(
        "info",
        aliases=["cat", "show"],
        help="Show detailed machine information",
        prog="machine info",
    )
    machine_info_group = machine_info_parser.add_mutually_exclusive_group(required=True)
    machine_info_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_info_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID",
    )
    machine_info_parser.set_defaults(action="info")

    def _machine_info(self, args: argparse.Namespace) -> None:
        """ Show detailed machine information 

            NOTE: This function is gross. I'm not sure of a cleaner way to build
            the pretty graphs and tables than manually like this. I need to
            research some other python modules that may be able to help
        """

        if args.assigned:
            m = self.cnxn.assigned
            if m is None:
                self.perror(f"no currently assigned machine")
                return
        else:
            # Convert to integer, if possible. Otherwise pass as-is
            try:
                machine_id = int(args.machine)
            except:
                machine_id = args.machine

            try:
                m = self.cnxn[machine_id]
            except KeyError:
                self.perror(f"{machine_id}: no such machine")
                return

        if m.spawned and not m.resetting and not m.terminating:
            state = f"{Fore.GREEN}up{Fore.RESET} for {m.expires}"
        elif m.terminating:
            state = f"{Fore.RED}terminating{Fore.RESET}"
        elif m.resetting:
            state = f"{Fore.YELLOW}resetting{Fore.RESET}"
        else:
            state = f"{Fore.RED}off{Fore.RESET}"

        if m.retired:
            retiree = f"{Fore.YELLOW}retired{Fore.YELLOW}"
        else:
            retiree = f"{Fore.GREEN}active{Fore.RESET}"

        try:
            os_icon = HackTheBox.OS_ICONS[m.os.lower()]
        except KeyError:
            os_icon = HackTheBox.OS_ICONS["other"]

        output = []
        output.append(
            f"{Style.BRIGHT}{Fore.GREEN}{m.name}{Fore.RESET} - {Style.RESET_ALL}{m.ip}{Style.BRIGHT} - {Style.RESET_ALL}{os_icon}{Style.BRIGHT} {Fore.CYAN}{m.os}{Fore.RESET} - {Fore.MAGENTA}{m.points}{Fore.RESET} points - {state}"
        )

        output.append("")
        output.append(f"{Style.BRIGHT}Difficulty{Style.RESET_ALL}")
        output.extend(["", "", "", "", ""])

        # Lookup tables for creating the difficulty ratings
        rating_char = [
            "\u2581",
            "\u2582",
            "\u2583",
            "\u2584",
            "\u2585",
            "\u2586",
            "\u2587",
            "\u2588",
        ]
        rating_color = [*([Fore.GREEN] * 3), *([Fore.YELLOW] * 4), *([Fore.RED] * 3)]

        # Create scaled difficulty rating. Highest rated is full. Everything
        # else is scaled appropriately.
        max_ratings = max(m.ratings)
        ratings = [round((float(r) / max_ratings) * 40) for r in m.ratings]
        difficulty = ""
        for i, r in enumerate(ratings):
            for row in range(1, 6):
                if r > (5 - row) * 8 and r <= (5 - row + 1) * 8:
                    output[-6 + row] += rating_color[i] + rating_char[r % 8] * 3
                elif r > (5 - row) * 8:
                    output[-6 + row] += rating_color[i] + rating_char[7] * 3
                else:
                    output[-6 + row] += "   "

        output.append(
            f"{Fore.GREEN}Easy     {Fore.YELLOW}   Medium   {Fore.RED}     Hard{Style.RESET_ALL}"
        )
        output.append("")
        output.append(
            f"{Style.BRIGHT}Rating Matrix ({Fore.CYAN}maker{Fore.RESET}, {Style.DIM}{Fore.GREEN}user{Style.RESET_ALL}{Style.BRIGHT}){Style.RESET_ALL}"
        )
        output.extend(["", "", "", "", ""])
        column_widths = [6, 8, 6, 8, 6]

        for i in range(5):
            for row in range(5):
                content = f"{'MMAA':^{column_widths[i]}}"
                if (m.matrix["maker"][i] * 4) >= ((row + 1) * 8):
                    content = content.replace("MM", f"{Fore.CYAN}{rating_char[7]*2}")
                elif (m.matrix["maker"][i] * 4) > (row * 8):
                    content = content.replace(
                        "MM",
                        f"{Fore.CYAN}{rating_char[round(m.matrix['maker'][i]*4) % 8]*2}",
                    )
                else:
                    content = content.replace("MM", " " * 2)
                if (m.matrix["aggregate"][i] * 4) >= ((row + 1) * 8):
                    content = content.replace(
                        "AA",
                        f"{Style.DIM}{Fore.GREEN}{rating_char[7]*2}{Style.RESET_ALL}",
                    )
                elif (m.matrix["aggregate"][i] * 4) > (row * 8):
                    content = content.replace(
                        "AA",
                        f"{Style.DIM}{Fore.GREEN}{rating_char[round(m.matrix['maker'][i]*4) % 8]*2}{Style.RESET_ALL}",
                    )
                else:
                    content = content.replace("AA", " " * 2)
                output[-1 - row] += content

        output.append(
            f"{'Enum':^{column_widths[0]}}{'R-Life':^{column_widths[1]}}{'CVE':^{column_widths[2]}}{'Custom':^{column_widths[3]}}{'CTF':^{column_widths[4]}}"
        )

        output.append("")

        user_width = max([6, len(m.blood["user"]["name"]) + 2])

        output.append(
            f"{Style.BRIGHT}      {'User':<{user_width}}Root{Style.RESET_ALL}"
        )
        output.append(
            f"{Style.BRIGHT}Owns  {Style.RESET_ALL}{Fore.YELLOW}{m.user_owns:<{user_width}}{Fore.RED}{m.root_owns}{Style.RESET_ALL}"
        )
        output.append(
            f"{Style.BRIGHT}{'Blood':<6}{Style.RESET_ALL}{m.blood['user']['name']:<{user_width}}{m.blood['root']['name']}"
        )

        self.ppaged("\n".join(output))

    machine_own_parser = machine_subparsers.add_parser(
        "own",
        aliases=["submit", "shutdown"],
        help="Submit a root or user flag",
        prog="machine own",
    )
    machine_own_parser.add_argument(
        "--rate",
        "-r",
        type=int,
        default=0,
        choices=range(1, 100),
        help="Difficulty Rating (1-100)",
    )
    machine_own_group = machine_own_parser.add_mutually_exclusive_group(required=True)
    machine_own_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_own_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID",
    )
    machine_own_parser.add_argument("flag", help="The user or root flag")
    machine_own_parser.set_defaults(action="own")

    def _machine_own(self, args: argparse.Namespace) -> None:
        """ Submit a machine own (user or root) """

        if args.assigned:
            m = self.cnxn.assigned
            if m is None:
                self.perror(f"no currently assigned machine")
                return
        else:
            # Convert to integer, if possible. Otherwise pass as-is
            try:
                machine_id = int(args.machine)
            except:
                machine_id = args.machine

            try:
                m = self.cnxn[machine_id]
            except KeyError:
                self.perror(f"{machine_id}: no such machine")
                return

        if m.submit(args.flag, difficulty=args.rate):
            self.psuccess(f"correct flag for {m.Name}!")
        else:
            self.perror(f"incorrect flag")

    machine_cancel_parser = machine_subparsers.add_parser(
        "cancel",
        description="Cancel a pending termination or reset for a machine",
        prog="machine cancel",
    )
    machine_cancel_parser.add_argument(
        "--termination",
        "-t",
        action="append_const",
        const="t",
        dest="cancel",
        help="Cancel a machine termination",
    )
    machine_cancel_parser.add_argument(
        "--reset",
        "-r",
        action="append_const",
        const="r",
        dest="cancel",
        help="Cancel a machine reset",
    )
    machine_cancel_parser.add_argument(
        "--both",
        "-b",
        action="store_const",
        const=[],
        dest="cancel",
        help="Cancel machine reset and termination",
    )
    machine_cancel_group = machine_cancel_parser.add_mutually_exclusive_group(
        required=True
    )
    machine_cancel_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_cancel_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID",
    )
    machine_cancel_parser.set_defaults(action="cancel", cancel=[])

    def _machine_cancel(self, args: argparse.Namespace) -> None:
        """ Cancel pending termination or reset """

        if args.assigned:
            m = self.cnxn.assigned
            if m is None:
                self.perror(f"no currently assigned machine")
                return
        else:
            # Convert to integer, if possible. Otherwise pass as-is
            try:
                machine_id = int(args.machine)
            except:
                machine_id = args.machine

            try:
                m = self.cnxn[machine_id]
            except KeyError:
                self.perror(f"{machine_id}: no such machine")
                return

        if len(args.cancel) == 0 or "t" in args.cancel:
            if m.terminating:
                m.terminating = False
                self.psuccess(f"{m.name}: pending termination cancelled")
        if len(args.cancel) == 0 or "r" in args.cancel:
            if m.resetting:
                m.resetting = False
                self.psuccess(f"{m.name}: pending reset cancelled")

    machine_init_parser = machine_subparsers.add_parser(
        "init", help="Perform intiial preliminary scans on host", prog="machine init"
    )
    machine_init_parser.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Location to build analysis directory (default: ./{machine-name}.{tld}",
    )
    machine_init_parser.add_argument(
        "--tld",
        "-t",
        type=str,
        default="htb",
        help="The Top-Level Domain (TLD) to use in the /etc/hosts file (default: htb)",
    )
    machine_init_group = machine_init_parser.add_mutually_exclusive_group(required=True)
    machine_init_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_init_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID to start",
    )
    machine_init_parser.set_defaults(action="init")

    def _machine_init(self, args: argparse.Namespace) -> None:
        """ Initialize a directory structure for starting analysis of a machine, and
        kick-off preliminary scans """

        # Use the assigned machine if requested
        if args.assigned:
            m = self.cnxn.assigned
            if m is None:
                self.perror(f"no currently assigned machine")
                return
        else:
            # Convert to integer, if possible. Otherwise pass as-is
            try:
                machine_id = int(args.machine)
            except:
                machine_id = args.machine

            # Lookup the given machine id
            try:
                m = self.cnxn[machine_id]
            except KeyError:
                self.perror(f"{machine_id}: no such machine")
                return

        # Build path if not specified
        if args.path is None:
            args.path = f"./{m.name.lower()}.{args.tld}"

        # Expand `~` in the path
        args.path = os.path.expanduser(args.path)

        # Ensure the directory doesn't exist yet
        if os.path.exists(args.path):
            self.perror(f"{args.path}: directory exists")
            return

        self.poutput("creating analysis directory tree")

        # Get full path
        args.path = os.path.abspath(args.path)

        # Create the directory
        self.poutput(f"  {args.path}")
        os.mkdir(args.path)

        # Create directory tree
        self.poutput(f"  {os.path.join(args.path, 'scans')}")
        os.makedirs(os.path.join(args.path, "scans"))
        self.poutput(f"  {os.path.join(args.path, 'artifacts')}")
        os.makedirs(os.path.join(args.path, "artifacts"))
        self.poutput(f"  {os.path.join(args.path, 'exploits')}")
        os.makedirs(os.path.join(args.path, "exploits"))
        self.poutput(f"  {os.path.join(args.path, 'img')}")
        os.makedirs(os.path.join(args.path, "img"))

        # Create initial readme
        self.poutput(f"creating initial readme")
        with open(os.path.join(args.path, "README.md"), "w") as f:
            f.write(
                f"""
# Hack the Box - {m.name} - {m.ip}

Preliminary scanning structure. Any completed scans are stored under `./scans`.
"""
            )

        # Add the host to /etc/hosts
        #   NOTE: I *really* don't like calling sudo like this...
        self.poutput(f"adding {m.name.lower()}.{args.tld} to /etc/hosts")
        line = f"\\n{m.ip}\\t{m.name.lower()}.{args.tld}\\n"
        line = f"echo -e {shlex.quote(line)} >> /etc/hosts"
        os.system(f"sudo /bin/sh -c {shlex.quote(line)}")

        # Perform initial scans
        self.poutput(f"starting preliminary scanners")
        htb.scanner.scan(self, args.path, f"{m.name.lower()}.{args.tld}", m)

    # Argument parser for `machine` command
    lab_parser = Cmd2ArgumentParser(description="View and manage lab VPN connection")
    lab_parser.set_defaults(action="status")
    lab_subparsers = lab_parser.add_subparsers(
        help="Actions", required=False, dest="_action"
    )

    @cmd2.with_argparser(lab_parser)
    @cmd2.with_category("Hack the Box")
    def do_lab(self, args: argparse.Namespace) -> bool:
        """ Execute the various lab sub-commands """
        actions = {
            "status": self._lab_status,
            "switch": self._lab_switch,
            "config": self._lab_config,
            "connect": self._lab_connect,
            "disconnect": self._lab_disconnect,
            "import": self._lab_import,
        }
        actions[args.action](args)
        return False

    lab_status_parser = lab_subparsers.add_parser(
        "status",
        description="Show the connection status of the currently assigned lab VPN",
        prog="lab status",
    )
    lab_status_parser.set_defaults(action="status")

    def _lab_status(self, args: argparse.Namespace) -> None:
        """ Print the lab VPN status """

        lab = self.cnxn.lab

        output = []

        output.append(
            f"{Style.BRIGHT}Server: {Style.RESET_ALL}{Fore.CYAN}{lab.name}{Fore.RESET} ({lab.hostname}:{lab.port})"
        )

        if lab.active:
            output.append(
                f"{Style.BRIGHT}Status: {Style.RESET_ALL}{Fore.GREEN}Connected{Fore.RESET}"
            )
            output.append(
                f"{Style.BRIGHT}IPv4 Address: {Style.RESET_ALL}{Style.DIM+Fore.GREEN}{lab.ipv4}{Style.RESET_ALL}"
            )
            output.append(
                f"{Style.BRIGHT}IPv6 Address: {Style.RESET_ALL}{Style.DIM+Fore.MAGENTA}{lab.ipv6}{Style.RESET_ALL}"
            )
            output.append(
                f"{Style.BRIGHT}Traffic: {Style.RESET_ALL}{Fore.GREEN}{lab.rate_up}{Fore.RESET} up, {Fore.CYAN}{lab.rate_down}{Fore.RESET} down"
            )
        else:
            output.append(
                f"{Style.BRIGHT}Status: {Style.RESET_ALL}{Fore.RED}Disconnected{Fore.RESET}"
            )

        self.poutput("\n".join(output))

    lab_switch_parser = lab_subparsers.add_parser(
        "switch",
        description="Show the connection status of the currently assigned lab VPN",
        prog="lab switch",
    )
    lab_switch_parser.add_argument(
        "lab", choices=VPN.VALID_LABS, type=str, help="The lab to switch to"
    )
    lab_switch_parser.set_defaults(action="switch")

    def _lab_switch(self, args: argparse.Namespace) -> None:
        """ Switch labs """
        try:
            self.cnxn.lab.switch(args.lab)
        except RequestFailed as e:
            self.perror(f"failed to switch: {e}")
        else:
            self.psuccess(f"lab switched to {args.lab}")

    lab_config_parser = lab_subparsers.add_parser(
        "config", description="Download OVPN configuration file", prog="lab config",
    )
    lab_config_parser.set_defaults(action="config")

    def _lab_config(self, args: argparse.Namespace) -> None:
        """ Download OVPN configuration file """
        try:
            self.poutput(self.cnxn.lab.config.decode("utf-8"), apply_style=False)
        except AuthFailure:
            self.perror("authentication failure (did you supply email/password?)")

    lab_connect_parser = lab_subparsers.add_parser(
        "connect",
        description="Connect to the Hack the Box VPN. If no previous configuration has been created in NetworkManager, it attempts to download it and import it.",
        prog="lab connect",
    )
    lab_connect_parser.add_argument(
        "--update",
        "-u",
        action="store_true",
        help="Force a redownload/import of the OpenVPN configuration",
    )
    lab_connect_parser.set_defaults(action="connect")

    def _lab_connect(self, args: argparse.Namespace) -> None:
        """ Connect to the Hack the Box VPN using NetworkManager """

        # Attempt to grab the VPN if it exists, and import it if it doesn't
        connection, uuid = self._nm_import_vpn(name="python-htb", force=False)
        if connection is None:
            # nm_import_vpn handles error output
            return

        # Check if this connection is active on any devices
        for active_connection in NetworkManager.NetworkManager.ActiveConnections:
            if active_connection.Uuid == uuid:
                self.poutput(f"vpn connection already active")
                return

        # Activate the connection
        for device in NetworkManager.NetworkManager.GetDevices():
            # Attempt to activate the VPN on each wired and wireless device...
            # I couldn't find a good way to do this intelligently other than
            # trying them until one worked...
            if (
                device.DeviceType == NetworkManager.NM_DEVICE_TYPE_ETHERNET
                or device.DeviceType == NetworkManager.NM_DEVICE_TYPE_WIFI
            ):
                try:
                    active_connection = NetworkManager.NetworkManager.ActivateConnection(
                        connection, device, "/"
                    )
                    if active_connection is None:
                        self.perror("failed to activate vpn connection")
                        return
                except dbus.exceptions.DBusException:
                    continue
                else:
                    break
        else:
            self.perror("vpn connection failed")
            return

        # Wait for VPN to become active or transition to failed
        while (
            active_connection.VpnState
            < NetworkManager.NM_VPN_CONNECTION_STATE_ACTIVATED
        ):
            time.sleep(0.5)

        if (
            active_connection.VpnState
            != NetworkManager.NM_VPN_CONNECTION_STATE_ACTIVATED
        ):
            self.perror("vpn connection failed")
            return

        self.psuccess(
            f"connected w/ ipv4 address: {active_connection.Ip4Config.Addresses[0][0]}/{active_connection.Ip4Config.Addresses[0][1]}"
        )

    lab_disconnect_parser = lab_subparsers.add_parser(
        "disconnect",
        description="Disconnect from the Hack the Box lab VPN",
        prog="lab disconnect",
    )
    lab_disconnect_parser.set_defaults(action="disconnect")

    def _lab_disconnect(self, args: argparse.Namespace) -> None:
        """ Disconnect from Hack the Box VPN via Network Manager """

        if "lab" not in self.config or "connection" not in self.config["lab"]:
            self.perror('lab vpn configuration not imported (hint: use "lab import")')
            return

        for c in NetworkManager.NetworkManager.ActiveConnections:
            if c.Uuid == self.config["lab"]["connection"]:
                NetworkManager.NetworkManager.DeactivateConnection(c)
                self.psuccess("vpn connection deactivated")
                break
        else:
            self.poutput("vpn connection not active or not found")

    lab_import_parser = lab_subparsers.add_parser(
        "import",
        description="Import your OpenVPN configuration into Network Manager",
        prog="lab import",
    )
    lab_import_parser.add_argument(
        "--reload",
        "-r",
        action="store_true",
        help="Reload configuration from Hack the Box",
    )
    lab_import_parser.add_argument(
        "--name", "-n", default="python-htb", help="NetworkManager Connection ID"
    )
    lab_import_parser.set_defaults(action="import")

    def _lab_import(self, args: argparse.Namespace) -> None:
        """ Import OpenVPN configuration into NetworkManager """

        # Import the connection
        c, uuid = self._nm_import_vpn(args.name, force=args.reload)

        # "nm_import_vpn" handles error/warning output
        if c is None:
            return

        self.psuccess(f"imported vpn configuration w/ uuid {uuid}")

    def _nm_import_vpn(self, name, force=True) -> NetworkManager.Connection:
        """ Import the VPN configuration with the specified name """

        # Ensure we aren't already managing a connection
        try:
            c, uuid = self._nm_get_vpn_connection()
            if force:
                c.Delete()
            else:
                return c, uuid
        except ConnectionNotFound:
            pass
        except InvalidConnectionID:
            self.pwarning("invalid connection id found in configuration; removing.")

        # We need to download and import the OVPN configuration file
        with tempfile.NamedTemporaryFile() as ovpn:
            # Write the configuration to a file
            ovpn.write(self.cnxn.lab.config)

            # Import the connection w/ Network Manager CLI
            p = subprocess.run(
                ["nmcli", "c", "import", "type", "openvpn", "file", ovpn.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if p.returncode != 0:
                self.perror("failed to import vpn configuration")
                self.perror(
                    "tip: try importing the config manually and fixing any network manager issues:\n\tnmcli connection import type openvpn file {your-ovpn-file}"
                )
                self.perror("nmcli stderr output:\n" + p.stderr.decode("utf-8"))
                return None, None

        # Parse the UUID out of the output
        try:
            uuid = p.stdout.split(b"(")[1].split(b")")[0].decode("utf-8")
        except:
            self.perror("unexpected output from nmcli")
            self.perror(
                "tip: try importing the config manually and fixing any network manager issues:\n\tnmcli connection import type openvpn file {your-ovpn-file}"
            )
            self.perror("nmcli stderr output:\n" + p.stderr.decode("utf-8"))
            self.perror("nmcli stdout output:\n" + p.stdout.decode("utf-8"))
            return None, None

        try:
            # Grab the connection object
            connection = NetworkManager.Settings.GetConnectionByUuid(uuid)

            # Ensure the routing settings are correct
            connection_settings = connection.GetSettings()
            connection_settings["connection"]["id"] = name
            connection_settings["ipv4"]["never-default"] = True
            connection_settings["ipv6"]["never-default"] = True
            connection.Update(connection_settings)
        except dbus.exceptions.DBusException as e:
            self.perror(f"dbus error during connection lookup: {e}")
            return None, None

        # Save the uuid in our configuration file
        self.config["lab"] = {}
        self.config["lab"]["connection"] = uuid
        with open(self.config_path, "w") as f:
            self.config.write(f)

        return connection, uuid

    def _nm_get_vpn_connection(self) -> NetworkManager.Connection:
        """ Grab the NetworkManager VPN configuration object """

        if "lab" not in self.config or "connection" not in self.config["lab"]:
            raise ConnectionNotFound

        try:
            # Grab the connection
            c = NetworkManager.Settings.GetConnectionByUuid(
                self.config["lab"]["connection"]
            )
        except dbus.exceptions.DBusException as e:
            raise InvalidConnectionID(str(e))

        return c, self.config["lab"]["connection"]

    @cmd2.with_category("Hack the Box")
    def do_invalidate(self, args) -> None:
        """ Invalidate API cache """
        self.cnxn.invalidate_cache()


def main():

    if "HTBRC" in os.environ:
        config = os.environ["HTBRC"]
    else:
        config = "~/.htbrc"

    # Build REPL object
    cmd = HackTheBox(resource=config)

    # Run remaning arguments as a command
    if len(sys.argv) > 1:
        cmd.onecmd(" ".join([shlex.quote(x) for x in sys.argv[1:]]))
        sys.exit(0)

    sys.exit(cmd.cmdloop())


if __name__ == "__main__":
    main()
