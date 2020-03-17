#!/usr/bin/env python3
from htb.scanner.scanner import Service, Scanner, Tracker
from htb.scanner.nikto import NiktoScanner
from htb.scanner.enum4linux import Enum4LinuxScanner
from htb.scanner.gobuster import GobusterScanner

AVAILABLE_SCANNERS = [NiktoScanner(), Enum4LinuxScanner(), GobusterScanner()]
