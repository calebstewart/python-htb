# Hack the Box Python API

A Python3 API for interacting with the Hack the Box platform.

## Fancy Showcase

Because a README doesn't do it justice, I recorded an `asciinema` of a small
subset of the functionality. You can see the output of the `machine info`
command and the automatic enumeration command `machine init`. The graphs don't
quite render properly in asciinema, but it should give you an idea of how the
tool works :)

[Asciinema Showcase](https://asciinema.org/a/hQbKBl3zbAYlNtpWQa2czyrff)

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
- Automatically build analysis directory structure and start basic
  enumeration/scans.
- Two Factor Authentication Support

## Example Configuration File

The `htb` command line application utilizes the `ConfigParser` module in Python
to read a configuration file from `~/.htbrc`. This file contains your
authentication information as well as any configuration items which may be
available. Here's an example of the configuration file:

```ini
[htb]
api_token = your_api_token
email = your_email
password = your_password
session = session_token
analysis_path = ~/htb

[lab]
connection = NetworkManager-Connection-UUID
```

The `connection` and `session` options are filled automatically on running to
track sessions between running `htb` and the connection which `htb lab` is able
to create with Network Manager.

This configuration is also passed to all scanners, allowing scanner specific
options to be specified. At this time, only one scanner utilizes the
configuraiton: `gobuster`. You can specify the worldist path under the
`gobuster` section. The default wordlist is the `dirbuster` small wordlist in
the Kali default wordlists directory. As an example, you can specify an
alternate like:

```ini
[gobuster]
wordlist = /usr/share/dirbuster/directory-list-lowercase-2.3-medium.txt
```

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

![List Active Machines](https://user-images.githubusercontent.com/7529189/76907462-a7487b00-687c-11ea-852f-87d566fcefd4.png)

Next, you can enter an interactive Hack the Box interpreter by
ommitting the command:

![Show Currently Assigned Machine Details](https://user-images.githubusercontent.com/7529189/76907463-a7487b00-687c-11ea-81cf-7c1efd3e0817.png)

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

### `machine enum`

Perform initial enumeration for the given machine. This will perform an
all-ports scan with `masscan`, and use the results to do an in-depth scan with
`nmap`. The results are saved under the `scans` directory for this machine.
Also, individual service results are parsed and saved in the `machine.json` file
at the root of the analysis directory. Future invocations of `htb` will be able
to read this and skip the initial enumeration phase.

```
htb ➜ machine enum --help
Usage: htb enum [-h] (--assigned | machine)

positional arguments:
  machine         A name regex, IP address or machine ID to start

optional arguments:
  -h, --help      show this help message and exit
  --assigned, -a  Perform action on the currently assigned machine
```

### `machine scan`

Perform basic scans which are applicable to enumerated services running on the
machine. You must complete the `enum` command first, or no matching services
will be located (because `htb` doesn't know what services are available). If a
scan is started in the foreground, you can background the scan with `C-z`.
Background jobs can be managed with the `jobs` command.

```
htb ➜ machine scan --help
Usage: machine scan [-h] [--service SERVICE] [--scanner SCANNER] [--recommended RECOMMENDED] [--background]
                    [--assigned]
                    [machine]

positional arguments:
  machine               A name regex, IP address or machine ID to start

optional arguments:
  -h, --help            show this help message and exit
  --service, -v SERVICE
                        Only run scans for this service (format: `{PORT}/{PROTOCOL}`)
  --scanner, -s SCANNER
                        Only run scans for this scanner
  --recommended, -r RECOMMENDED
                        Run all recommended scans
  --background, -b      Run scans in the background
  --assigned, -a        Perform action on the currently assigned machine
```

### `jobs list`

List all background jobs. This includes completed and running jobs, and will
output the status if any is available from the individual scanner.

```
htb ➜ jobs list --help
Usage: jobs list [-h]

List background scanner jobs and their status

optional arguments:
  -h, --help  show this help message and exit
```

### `jobs kill`

Kill the specified job ID. The job ID can be retrieved from the `jobs list`
command.

```
htb ➜ jobs kill --help
Usage: jobs kill [-h] job_id

Stop a running background scanner job

positional arguments:
  job_id      Kill the identified job

optional arguments:
  -h, --help  show this help message and exit
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

### `lab import`

This command will retrieve you lab configuration and import it into
NetworkManager. Obviously, you need to use Network Manager to manager your
network cards for this to work properly. You also need the Network Manager
OpenVPN plugin. The connection is managed by `htb` and the UUID is saved in your
configuration file. 

```
htb ➜ lab import --help
Usage: lab import [-h] [--reload] [--name NAME]

Import your OpenVPN configuration into Network Manager

optional arguments:
  -h, --help       show this help message and exit
  --reload, -r     Reload configuration from Hack the Box
  --name, -n NAME  NetworkManager Connection ID
```

### `lab connect`

This command will attempt to connect with Network Manager to the Hack the Box
VPN. If the connection has not been imported, it will automoatically import the
configuration. It looks for the connection specified by UUID in your
configuration file.

```
htb ➜ lab connect --help
Usage: lab connect [-h] [--update]

Connect to the Hack the Box VPN. If no previous configuration has been created in NetworkManager, it attempts to download it and import it.

optional arguments:
  -h, --help    show this help message and exit
  --update, -u  Force a redownload/import of the OpenVPN configuration
```

### `lab disconnect`

Disconnect the Network Manager connection referring to the Hack the Box
connection (specified in your configuration file).

```
htb ➜ lab connect --help
Usage: lab connect [-h] [--update]

Connect to the Hack the Box VPN. If no previous configuration has been created in NetworkManager, it attempts to download it and import it.

optional arguments:
  -h, --help    show this help message and exit
  --update, -u  Force a redownload/import of the OpenVPN configuration
```

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
