#!/usr/bin/env python3
from typing import Any
import cmd2
from cmd2 import Cmd
from cmd2.argparse_custom import Cmd2ArgumentParser
import configparser
import NetworkManager
import subprocess
from colorama import Fore, Style, Back
import queue
import argparse
import os.path
import tempfile
import signal
import shlex
import time
import dbus
import sys
import os

from htb import util
from htb import Connection, Machine, VPN
from htb.exceptions import *
from htb.scanner.scanner import Tracker, Scanner, Service
from htb.scanner import AVAILABLE_SCANNERS
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
        session = parser["htb"].get("session", None)

        if session is not None:
            self.pwarning("attempting to use existing session")

        # Ensure we have an API token
        if api_token is None:
            raise RuntimeError("no api token provided!")

        # Construct the connection object
        self.cnxn: Connection = Connection(
            api_token=api_token,
            email=email,
            password=password,
            existing_session=session,
            analysis_path=self.config["htb"].get("analysis_path", "~/htb"),
            twofactor_prompt=self.twofactor_prompt,
        )

        self.prompt = (
            f"{Fore.CYAN}htb{Fore.RESET} {Style.BRIGHT+Fore.GREEN}➜{Style.RESET_ALL} "
        )

        # List of job trackers
        self.jobs: List[Tracker] = []
        self.job_events: queue.Queue = queue.Queue()

        # Enable self in python
        self.self_in_py = True

        # Aliases
        self.aliases["exit"] = "quit"

    def twofactor_prompt(self) -> None:
        self.pwarning("One Time Password: ", end="")
        sys.stderr.flush()
        return self.read_input("")

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

    jobs_parser = Cmd2ArgumentParser(description="Manage background scanner jobs")
    jobs_parser.set_defaults(action="list")
    jobs_subparsers = jobs_parser.add_subparsers(help="Actions", dest="_action")

    @cmd2.with_argparser(jobs_parser)
    @cmd2.with_category("Management")
    def do_jobs(self, args: argparse.Namespace) -> bool:
        """ Manage running background scanner jobs """

        actions = {"list": self._jobs_list, "kill": self._jobs_kill}
        actions[args.action](args)
        return False

    jobs_list_parser = jobs_subparsers.add_parser(
        "list",
        aliases=["ls"],
        description="List background scanner jobs and their status",
        prog="jobs list",
    )
    jobs_list_parser.set_defaults(action="list")

    def _jobs_list(self, args: argparse.Namespace) -> None:
        """ List the background scanner jobs """

        # Grab any pending events
        try:
            while True:
                t = self.job_events.get_nowait()
                t.thread.join()
                t.thread = None
                # t.status = "completed"
        except queue.Empty:
            pass

        table = [["", "Host", "Service", "Scanner", "Status"]]
        for ident, job in enumerate(self.jobs):
            style = Style.DIM if job.thread is None else ""
            table.append(
                [
                    ">" + style + str(ident),
                    job.machine.name,
                    f"{job.service.port}/{job.service.protocol} ({job.service.name})",
                    job.scanner.name,
                    job.status,
                ]
            )

        self.ppaged("\n".join(util.build_table(table)))

    jobs_kill_parser = jobs_subparsers.add_parser(
        "kill",
        aliases=["rm", "stop"],
        description="Stop a running background scanner job",
        prog="jobs kill",
    )
    jobs_kill_parser.add_argument("job_id", type=int, help="Kill the identified job")
    jobs_kill_parser.set_defaults(action="kill")

    def _jobs_kill(self, args: argparse.Namespace) -> None:
        """ Stop a running background scanner job """

        # Ensure the job exists
        if args.job_id < 0 or args.job_id >= len(self.jobs):
            self.perror(f"{args.job_id}: no such job")
            return

        job = self.jobs[args.job_id]
        if job.thread is None:
            self.pwarning(f"{args.job_id}: already completed")
            return

        # Inform it should stop
        self.poutput(f"killing job {args.job_id}")
        job.stop = True

    # Argument parser for `machine` command
    machine_parser = Cmd2ArgumentParser(
        description="View and manage active and retired machines"
    )
    machine_parser.set_defaults(action="list")
    machine_subparsers = machine_parser.add_subparsers(help="Actions", dest="_action")

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
            "scan": self._machine_scan,
            "enum": self._machine_enum,
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

        # Build initial table with headers
        table = [["", "", "Name", "Address", "Difficulty", "Rate", "Owned", "State"]]

        # Create the individual machine rows
        for m in machines:
            style = Style.DIM if m.owned_user and m.owned_root else ""

            # Create scaled difficulty rating. Highest rated is full. Everything
            # else is scaled appropriately.
            max_ratings = max(m.ratings)
            if max_ratings == 0:
                ratings = m.ratings
            else:
                ratings = [float(r) / max_ratings for r in m.ratings]
            difficulty = ""
            for i, r in enumerate(ratings):
                difficulty += rating_color[i] + rating_char[round(r * 6)]
            difficulty += Style.RESET_ALL

            # "$" for user and "#" for root
            owned = f"^{'$' if m.owned_user else ' '} {'#' if m.owned_root else ' '}"

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
                state = Fore.BLUE + state + Fore.RESET
                assigned = f"{Fore.BLUE}*{Style.RESET_ALL} "
            else:
                assigned = " "

            table.append(
                [
                    f"{style}{m.id}",
                    assigned,
                    m.name,
                    m.ip,
                    difficulty,
                    f"{m.rating:.1f}",
                    owned,
                    state,
                ]
            )

        # print data
        self.ppaged("\n".join(util.build_table(table)))

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

        self.psuccess(f"{m.name}: scheduling reset")
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
            except KeyError as e:
                self.perror(f"{machine_id}: no such machine: {e}")
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

    machine_enum_parser = machine_subparsers.add_parser(
        "enum", aliases=["enumerate"], help="Perform initial service enumeration"
    )
    machine_enum_group = machine_enum_parser.add_mutually_exclusive_group(required=True)
    machine_enum_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_enum_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID to start",
    )
    machine_enum_parser.set_defaults(action="enum")

    def _machine_enum(self, args: argparse.Namespace) -> None:
        """ Perform initial service enumeration """

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

        if m.analysis_path is None:
            self.pwarning("initializing analysis structure")

            try:
                m.init(self.cnxn.analysis_path)
            # except OSError as e:
            #     self.perror(f"failed to create directory structure: {e}")
            #     return
            except EtcHostsFailed:
                self.perror("failed to add host to /etc/hosts")
                return

        if len(m.services) == 0:
            self.poutput("enumerating machine services")
            try:
                m.enumerate()
            except MasscanFailed:
                self.perror("masscan failed")
            except NmapFailed:
                self.perror("nmap failed")
        else:
            self.poutput(
                f"{m.name} already enumerated ({len(m.services)} service(s) detected)"
            )

    machine_scan_parser = machine_subparsers.add_parser(
        "scan",
        help="Perform prepared applicable scans against this host",
        prog="machine scan",
    )
    machine_scan_parser.add_argument(
        "--service",
        "-v",
        help="Only run scans for this service (format: `{PORT}/{PROTOCOL}`)",
    )
    machine_scan_parser.add_argument(
        "--scanner", "-s", help="Only run scans for this scanner"
    )
    machine_scan_parser.add_argument(
        "--recommended", "-r", help="Run all recommended scans"
    )
    machine_scan_parser.add_argument(
        "--background",
        "-b",
        help="Run scans in the background",
        action="store_true",
        default=False,
    )
    machine_scan_group = machine_scan_parser.add_mutually_exclusive_group(required=True)
    machine_scan_group.add_argument(
        "--assigned",
        "-a",
        action="store_true",
        help="Perform action on the currently assigned machine",
        default=False,
    )
    machine_scan_group.add_argument(
        "machine", nargs="?", help="A name regex, IP address or machine ID to start",
    )
    machine_scan_parser.set_defaults(action="scan")

    def _machine_scan(self, args: argparse.Namespace) -> None:
        """ Scan the open service for the given machine """

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

        if args.recommended:
            scanners = [s for s in AVAILABLE_SCANNERS if s.recommended and s.match(m)]
        elif args.scanner:
            scanners = [s for s in AVAILABLE_SCANNERS if s.name == args.scanner]
        else:
            scanners = [s for s in AVAILABLE_SCANNERS if s.match(m)]

        if args.service:
            port = int(args.service.split("/")[0])
            protocol = args.service.split("/")[1]
            services = [
                s for s in m.services if s.port == port and s.protocol == protocol
            ]
        else:
            services = m.services

        if len(services) == 0:
            self.perror("no matching services found")
            return

        # Get scanners that match a service specified/present
        if args.recommended:
            scanners = [
                s
                for s in scanners
                if s.recommended and any([s.match_service(svc) for svc in services])
            ]
        elif args.scanner:
            scanners = [
                s
                for s in scanners
                if s.name == args.scanner
                and any([s.match_service(svc) for svc in services])
            ]
        else:
            scanners = [
                s for s in scanners if any([s.match_service(svc) for svc in services])
            ]

        if len(scanners) == 0:
            self.perror(f"no matching scanners found")
            return

        # Iterate over all scanners and services to run the correct scans
        for service in services:
            for scanner in scanners:
                if not scanner.match_service(service):
                    continue

                self.poutput(
                    f"beginning {scanner.name} scan on {service.port}/{service.protocol} ({service.name})"
                )
                tracker = m.scan(scanner, service, silent=args.background)
                if args.background:
                    # Transfer control of the scan to the `jobs` command
                    tracker.events = self.job_events
                    tracker.lock.release()
                    self.jobs.append(tracker)
                else:
                    # Monitor the scan progress in the forground, and give
                    # options to cancel or background the scan
                    self.monitor_scan(tracker)

    def monitor_scan(self, tracker: Tracker) -> None:
        """ Monitor a foreground scan """

        # Setup local event queue for completion
        events = queue.Queue()
        tracker.job_events = events
        tracker.lock.release()

        # Exception used when C-z is pressed to background a task
        class GoToSleep(Exception):
            pass

        def background_me(signo, stack):
            """ Transfer running task to background thread """
            # Turn off the signal handler
            signal.signal(signal.SIGTSTP, signal.SIG_DFL)
            raise GoToSleep

        try:
            # Register C-z handler
            signal.signal(signal.SIGTSTP, background_me)

            try:
                tracker = tracker.job_events.get()
            except KeyboardInterrupt:
                self.pwarning(
                    f"cancelling {tracker.scanner.name} for {tracker.service.port}/{tracker.service.protocol}"
                )
                tracker.stop = True

            # Restore previous signal
            signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        except GoToSleep:
            with tracker.lock:
                self.pwarning(
                    f"backgrounding {tracker.scanner.name} for {tracker.service.port}/{tracker.service.protocol}"
                )
                tracker.silent = True
                tracker.events = self.job_events
                self.jobs.append(tracker)

    # Argument parser for `machine` command
    lab_parser = Cmd2ArgumentParser(description="View and manage lab VPN connection")
    lab_parser.set_defaults(action="status")
    lab_subparsers = lab_parser.add_subparsers(help="Actions", dest="_action")

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
    cmd = HackTheBox(resource=config, allow_cli_args=False)

    # Run remaning arguments as a command
    if len(sys.argv) > 1:
        cmd.onecmd(" ".join([shlex.quote(x) for x in sys.argv[1:]]))
        if len([j for j in cmd.jobs if j.thread is not None]):
            cmd.pwarning("background jobs active. staring interpreter...")
            result = cmd.cmdloop()
        else:
            result = 0
    else:
        result = cmd.cmdloop()

    try:
        if len([j for j in cmd.jobs if j.thread is not None]):
            cmd.poutput("waiting for background jobs to complete")
        while len([j for j in cmd.jobs if j.thread is not None]):
            tracker = cmd.job_events.get()
            tracker.status = "completed"
            tracker.thread = None
    except KeyboardInterrupt:
        cmd.pwarning("cancelling background jobs")
        for j in cmd.jobs:
            j.stop = True

        try:
            while len([j for j in cmd.jobs if j.thread is not None]):
                tracker = cmd.job_events.get()
                tracker.status = "completed"
                tracker.thread = None
        except KeyboardInterrupt:
            cmd.pwarning("forcing background job exit!")
            for j in [j for j in cmd.jobs if j.thread is not None]:
                j.thread.daemon = True

    cmd.config["htb"]["session"] = cmd.cnxn.session.cookies.get(
        "hackthebox_session", default="", domain="www.hackthebox.eu"
    )
    with open(os.path.expanduser(config), "w") as f:
        cmd.config.write(f)

    for m in cmd.cnxn.machines:
        if m.dump():
            cmd.poutput(f"saved enumeration data for {m.name}")


if __name__ == "__main__":
    main()
