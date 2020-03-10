#!/usr/bin/env python3
import cmd2
from cmd2 import Cmd
from cmd2.argparse_custom import Cmd2ArgumentParser
import configparser
from colorama import Fore, Style, Back
import argparse
import shlex
import sys
import os

from htb import Connection, Machine, VPN
from htb.exceptions import RequestFailed, AuthFailure


class HackTheBox(Cmd):
    """ Hack the Box Command Line Interface """

    def __init__(self, resource="~/.htbrc", *args, **kwargs):
        super(HackTheBox, self).__init__(*args, **kwargs)

        # Find file location referencing "~"
        path_resource = os.path.expanduser(resource)
        if not os.path.isfile(path_resource):
            raise RuntimeError(f"{resource}: no such file or directory")

        # Read configuration
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path_resource)

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

        self.prompt = "htb ➜ "

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
            self.perror(f"[!] {a.name} already assigned to you")
            return

        if m is None:
            self.perror(f"[!] {machine_id}: no such machine")
            return

        if m.spawned:
            self.poutput(f"[+] {m.name}: already running. did you mean 'transfer'?")
            return

        self.poutput(f"[+] starting {m.name}")
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
            self.perror(f"[!] {machine_id}: no such machine")
            return

        if not m.spawned:
            self.poutput(f"[+] {m.name}: not running")
            return

        self.poutput(f"[+] {m.name}: scheduling reset")
        m.resetting = True

    machine_stop_parser = machine_subparsers.add_parser(
        "stop", aliases=["down", "shutdown"], help="Stop a machine", prog="machine down"
    )
    machine_stop_parser.add_argument(
        "machine", help="A name regex, IP address or machine ID to start"
    )
    machine_stop_parser.set_defaults(action="stop")

    def _machine_stop(self, args: argparse.Namespace) -> None:
        """ Stop an active machine """

        # Convert to integer, if possible. Otherwise pass as-is
        try:
            machine_id = int(args.machine)
        except:
            machine_id = args.machine

        m = self.cnxn[machine_id]
        a = self.cnxn.assigned

        if m is None:
            self.perror(f"[!] {machine_id}: no such machine")
            return

        if not m.spawned:
            self.poutput(f"[+] {m.name} is not running")
            return

        self.poutput(f"[+] scheduling termination for {m.name}")
        m.spawned = True

    machine_info_parser = machine_subparsers.add_parser(
        "info",
        aliases=["cat", "show"],
        help="Show detailed machine information",
        prog="machine info",
    )
    machine_info_parser.add_argument(
        "machine", help="A name regex, IP address or machine ID to show"
    )
    machine_info_parser.set_defaults(action="info")

    def _machine_info(self, args: argparse.Namespace) -> None:
        """ Show detailed machine information 

            NOTE: This function is gross. I'm not sure of a cleaner way to build
            the pretty graphs and tables than manually like this. I need to
            research some other python modules that may be able to help
        """

        try:
            machine_id = int(args.machine)
        except:
            machine_id = args.machine

        try:
            m = self.cnxn[args.machine]
        except KeyError:
            self.perror(f"[!] {machine_id}: no such machine")

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

        output = []
        output.append(
            f"{Style.BRIGHT}{Fore.GREEN}{m.name}{Fore.RESET} - {Style.RESET_ALL}{m.ip}{Style.BRIGHT} - {Fore.CYAN}{m.os}{Fore.RESET} - {Fore.MAGENTA}{m.points}{Fore.RESET} points - {state}"
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
        column_widths = [6, 8, 6, 10, 6]

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
            f"{'Enum':^{column_widths[0]}}{'R-Life':^{column_widths[1]}}{'CVE':^{column_widths[2]}}{'Exploit':^{column_widths[3]}}{'CTF':^{column_widths[4]}}"
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
    machine_own_parser.add_argument(
        "machine", help="A name regex, IP address or machine ID to start"
    )
    machine_own_parser.add_argument("flag", help="The user or root flag")
    machine_own_parser.set_defaults(action="own")

    def _machine_own(self, args: argparse.Namespace) -> None:
        """ Submit a machine own (user or root) """

        try:
            machine_id = int(args.machine)
        except:
            machine_id = args.machine

        try:
            m = self.cnxn[machine_id]
        except KeyError:
            self.perror(f"[!] {machine_id}: no such machine")
            return

        if m.submit(args.flag, difficulty=args.rate):
            self.poutput(f"[+] correct flag for {m.Name}!")
        else:
            self.poutput(f"[-] incorrect flag")

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
        "--all",
        "-a",
        action="store_const",
        const=[],
        dest="cancel",
        help="Cancel machine reset and termination",
    )
    machine_cancel_parser.add_argument(
        "machine", help="A name regex, IP address or machine ID"
    )
    machine_cancel_parser.set_defaults(action="cancel", cancel=[])

    def _machine_cancel(self, args: argparse.Namespace) -> None:
        """ Cancel pending termination or reset """

        try:
            machine_id = int(args.machine)
        except:
            machine_id = args.machine

        try:
            m = self.cnxn[machine_id]
        except:
            self.perror(f"[!] {machine_id}: no such machine")
            return

        if len(args.cancel) == 0 or "t" in args.cancel:
            if m.terminating:
                m.terminating = False
                self.poutput(f"[+] {m.name}: pending terminating cancelled")
        if len(args.cancel) == 0 or "r" in args.cancel:
            if m.resetting:
                m.resetting = False
                self.poutput(f"[+] {m.name}: pending reset cancelled")

    # Argument parser for `machine` command
    lab_parser = Cmd2ArgumentParser(description="View and manage lab VPN connection")
    lab_parser.set_defaults(action="status")
    lab_subparsers = lab_parser.add_subparsers(
        help="Actions", required=False, dest="_action"
    )

    @cmd2.with_argparser(lab_parser)
    def do_lab(self, args: argparse.Namespace) -> bool:
        """ Execute the various lab sub-commands """
        actions = {
            "status": self._lab_status,
            "switch": self._lab_switch,
            "config": self._lab_config,
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
            self.perror(f"[!] failed to switch: {e}")
        else:
            self.poutput(f"[+] lab switched to {args.lab}")

    lab_config_parser = lab_subparsers.add_parser(
        "config", description="Download OVPN configuration file", prog="lab config",
    )
    lab_config_parser.set_defaults(action="config")

    def _lab_config(self, args: argparse.Namespace) -> None:
        """ Download OVPN configuration file """
        try:
            self.poutput(self.cnxn.lab.config.decode("utf-8"))
        except AuthFailure:
            self.perror("[!] authentication failure (did you supply email/password?)")

    def do_invalidate(self, args) -> None:
        """ Invalidate API cache """
        self.cnxn.invalidate_cache()


def main():

    # Build argument parser
    parser = argparse.ArgumentParser(
        description="Python3 API for the Hack the Box Platform", prog="htb"
    )
    parser.add_argument("--config", "-c", required=False, type=str, default="~/.htbrc")

    # Parse arguments
    args, remaining = parser.parse_known_args()

    # Build REPL object
    cmd = HackTheBox(resource=args.config)

    # Run remaning arguments as a command
    if len(remaining):
        cmd.onecmd(" ".join([shlex.quote(x) for x in remaining]))
        sys.exit(0)

    sys.exit(cmd.cmdloop())


if __name__ == "__main__":
    main()
