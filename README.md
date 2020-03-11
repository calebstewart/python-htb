# Hack the Box Python API

A Python3 API for interacting with the Hack the Box platform.

## Features

- Connect to hack the box with `api_token` with an optional connection with
  E-Mail/Password
- List machines (active/retired/running/assigned/etc)
- Query VPN status (Labs and Fortress)
- Switch VPN assignment (only for labs VPN)
- Grab OVPN configuration (requires E-mail/password credentials)
- Start and stop machines (w/ VIP this works for all machines, only active
  machines are supported for free labs)
- Cancel termination or reset of machines
- Send messages to the Shoutbox (including `/{command}` commands)
- Command line interface

## Example Command Line Usage

The Command Line Interface provides two methods for invocation. The first
simply runs a single command and exits. This is the type of invocation you
can expect from a shellscript. By default, the configuration information
is read from a file located at `$HOME/.htbrc`, but can also be specified 
with the environment variable `HTBRC`.

To get a list of valid commands, you can use the `help` command:

```
python-htb on  master [!] via python-htb took 2s 
➜ python -m htb help -v    

Documented commands (use 'help -v' for verbose/'help <topic>' for details):

Hack the Box
================================================================================
invalidate          Invalidate API cache
lab                 View and manage lab VPN connection
machine             View and manage active and retired machines

Uncategorized
================================================================================
alias               Manage aliases
edit                Run a text editor and optionally open a file with it
help                List available commands or provide detailed help for a specific command
history             View, run, edit, save, or clear previously entered commands
macro               Manage macros
py                  Invoke Python command or shell
quit                Exit this application
run_pyscript        Run a Python script file inside the console
run_script          Run commands in script file that is encoded as either ASCII or UTF-8 text
set                 Set a settable parameter or show current settings of parameters
shell               Execute a command as if at the OS prompt
shortcuts           List available shortcuts
```

To run a command, simply append it to the command line when invoking the module.
This is the first method of invocation:

```
$ python -m htb machine list --active
      Name         Address        Difficulty Rate Owned  State
200   Rope         10.10.10.148   ▂▁▁▁▁▁▂▃▄▇ 4.6   $ #   off
211   Sniper       10.10.10.151   ▁▁▂▄▂▇▇▅▂▂ 4.6   $     off
212   Forest       10.10.10.161   ▂▂▅▆▂▆▇▆▃▃ 4.6   $ #   11 hours
213   Registry     10.10.10.159   ▂▂▄▆▂▆▇▅▃▂ 4.5   $ #   off
214   Mango        10.10.10.162   ▃▄▆▇▂▆▅▃▂▂ 4.0   $ #   22 hours
215   Postman      10.10.10.160   ▃▄▇▇▂▃▃▂▁▁ 4.0   $ #   off
217   Traverxec    10.10.10.165   ▂▃▇▇▂▄▄▂▁▂ 4.3   $ #   22 hours
218   Control      10.10.10.167   ▂▁▂▄▂▆▇▆▃▄ 4.5         off
219   Obscurity    10.10.10.168   ▃▄▇▇▂▄▄▂▂▂ 3.9   $ #   14 hours
220   Resolute     10.10.10.169   ▃▄▇▆▂▅▄▃▁▂ 4.7   $ #   13 hours
221   PlayerTwo    10.10.10.170   ▂▁▁▁▁▂▃▃▄▇ 4.2         off
222   OpenAdmin    10.10.10.171   ▅▅▇▆▂▃▃▂▁▁ 4.4   $ #   17 hours
223   Monteverde   10.10.10.172   ▂▃▇▇▂▄▄▂▁▂ 4.3   $     off
224   Patents      10.10.10.173   ▁▁▁▁▁▂▂▃▃▇ 3.7         off
225   Nest         10.10.10.178   ▃▃▅▇▂▅▅▃▂▂ 3.9   $ #   14 hours
227   Fatty        10.10.10.174   ▁▁▁▁▁▂▂▃▄▇ 4.4   $ #   off
229   Sauna        10.10.10.175   ▂▃▇▇▂▄▃▂▁▂ 4.2   $     11 hours
230 * Book         10.10.10.176   ▂▁▂▃▂▅▇▅▃▃ 3.8         23 hours
231   Oouch        10.10.10.177   ▁▁▁▁▁▁▂▃▄▇ 4.6         17 hours
232   Multimaster  10.10.10.179   ▃▁▂▁▁▂▃▅▂▇ 1.4         22 hours
```

Next, you can enter an interactive Hack the Box interpreter by
ommitting the command:

```
python-htb on  master [!] via python-htb took 3s 
➜ python -m htb machine info --assigned
Sniper - 10.10.10.151 - Windows - 30 points - up for 23 hours

Difficulty
               ▆▆▆▁▁▁         
               ██████▂▂▂      
         ▃▃▃   █████████      
      ▂▂▂███   █████████▂▂▂▃▃▃
▃▃▃▃▃▃████████████████████████
Easy        Medium        Hard

Rating Matrix (maker, user)
        ▅▅                          
 ██▁▁   ████           ██           
 ████   ████     ▁▁    ██▁▁         
 ████   ████     ██    ████         
 ████   ████   ████    ████    ▅▅██ 
 Enum  R-Life  CVE   Exploit   CTF  

      User      Root
Owns  1991      1769
Blood snowscan  snowscan
```

## Available Commands

### `machine list`

List available machines on the Hack the Box platform. Results are paged if too
numerous to fit on screen and not redirected. Currently assigned machine is
highlighted by an asterics following the machine ID.

```
htb ➜ machine list --help
Usage: machine list [-h] [--inactive] [--active] [--owned] [--unowned] [--todo]

optional arguments:
  -h, --help      show this help message and exit
  --inactive, -i
  --active, -a
  --owned, -o
  --unowned, -u
  --todo, -t
```

### `machine info`

Display detailed machine information. This includes difficulty graph and rating
matrix (both user and maker).

```
htb ➜ machine info --help
Usage: machine info [-h] (--assigned | machine)

positional arguments:
  machine         A name regex, IP address or machine ID

optional arguments:
  -h, --help      show this help message and exit
  --assigned, -a  Perform action on the currently assigned machine
```

### `machine up`

Start a machine instance in your current lab. This command is only valid for
VIP users, and will fail if another machine is already assigned to your
account.

```
htb ➜ machine up --help
Usage: machine up [-h] machine

positional arguments:
  machine     A name regex, IP address or machine ID to start

optional arguments:
  -h, --help  show this help message and exit
```

### `machine reset`

Issue a reset for the given machine. Resets happen after two minutes and can be
cancelled by other users in your lab. Check the `info` or `list` output for this
machine periodically after issuing to see if another user cancelled your reset.

```
htb ➜ machine reset --help
Usage: machine reset [-h] machine

positional arguments:
  machine     A name regex, IP address or machine ID

optional arguments:
  -h, --help  show this help message and exit
```

### `machine own`

Submit a user or root flag for a given machine. If no rating is specified, a rating
of `0` is submitted (same as default on website).

```
htb ➜ machine own --help
Usage: machine own [-h]
                   [--rate {1-100}]
                   [--assigned]
                   [machine] flag

positional arguments:
  machine               A name regex, IP address or machine ID
  flag                  The user or root flag

optional arguments:
  -h, --help            show this help message and exit
  --rate, -r {1-100}
                        Difficulty Rating (1-100)
  --assigned, -a        Perform action on the currently assigned machine
```

### `machine init`

Setup a directory tree for machine analysis and perform initial scans. This
routine will create the following directory tree:

- {machine.name}.htb/
  - artifacts/
  - exploits/
  - scans/
  - img/
  - README.md

It then adds the given machine to `/etc/hosts`, ensures the machine is running
and then starts a variety of basic scans on the target. Currently, the scans
aren't implemented yet, but they will eventually look similar to the basic
structure of my [init-machine](https://github.com/calebstewart/init-machine)
script.

```
htb ➜ machine init --help
Usage: machine init [-h] [--path PATH] [--tld TLD] (--assigned | machine)

positional arguments:
  machine          A name regex, IP address or machine ID to start

optional arguments:
  -h, --help       show this help message and exit
  --path, -p PATH  Location to build analysis directory (default: ./{machine-name}.{tld}
  --tld, -t TLD    The Top-Level Domain (TLD) to use in the /etc/hosts file (default: htb)
  --assigned, -a   Perform action on the currently assigned machine
```

### `lab status`

Display the current status of the lab VPN connection.

### `lab switch`

Change VPN servers.

```
htb ➜ lab switch --help
Usage: lab switch [-h] {usfree, usvip, eufree, euvip, aufree}

Show the connection status of the currently assigned lab VPN

positional arguments:
  {usfree, usvip, eufree, euvip, aufree}
                        The lab to switch to

optional arguments:
  -h, --help            show this help message and exit
```

### `lab config`

This command retrieves and outputs the contents of your OVPN configuration
file. An E-mail and password must be set in your configuration file for
this call to work (`api_token` alone is **not** enough).

### `invalidate`

The connection object maintains an API response cache by default for up to
one minute. This command will flush/invalidate the cache in order to force
a refresh of the data in the connection object. If you notice stale
information or require the most up to date machine status, then use this
command. It is not useful from the CLI interface. It only has relevance
from a long-running REPL context.

## Example Module Usage

```python
import htb

# Connect to hack the box
cnxn = htb.Connection(
	api_token="YOUR_API_TOKEN"
	email="YOUR_EMAIL",
	password="YOUR_PASSWORD",
)

# Switch to the US VIP lab
cnxn.lab.switch(htb.VPN.US_VIP)

# Save your OVPN configuration (requires email/password)
with open("htb.ovpn", "wb") as f:
	f.write(cnxn.lab.config)

# Grab the mango box by name and start it
cnxn["mango"].spawned = True

# Cancel a reset on Bastion (ip 10.10.10.137)
cnxn["10.10.10.137"].resetting = False

# Schedule termination on Registry (id 213)
cnxn[213].terminating = True

# Cancel all machine resets (probably shouldn't do this...)
for m in filter(lambda m: m.resetting, cnxn.machines):
	m.resetting = False
```
