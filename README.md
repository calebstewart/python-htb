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

## Planned Features

- Send messages to the Shoutbox (including `/{command}` commands)
- Recieve new messages from Shoutbox
- Command line interface (e.g. `python -m htb machines active` to list all
  active machines)

## Example Command Line Usage

The Command Line Interface provides two methods for invocation. The first
simply runs a single command and exits. This is the type of invocation you
can expect from a shellscript. By default, the configuration information
is read from a file located at `$HOME/.htbrc`, but can be changed. 

To get a list of command line options, you can use `--help`:

```
$ python -m htb --help
usage: htb [-h] [--config CONFIG]

Python3 API for the Hack the Box Platform

optional arguments:
  -h, --help            show this help message and exit
  --config CONFIG, -c CONFIG
```

To get a list of valid commands, you can use the `help` command:

```
$ python -m htb help
Documented commands (use 'help -v' for verbose/'help <topic>' for details):

Hack the Box
================================================================================
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

To run a command, simply append it to your call. This is the first method of invocation:

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
$ python -m htb
htb ➜ machine list --active
      Name         Address        Difficulty Rate Owned  State
200   Rope         10.10.10.148   ▂▁▁▁▁▁▂▃▄▇ 4.6   $ #   off
211   Sniper       10.10.10.151   ▁▁▂▄▂▇▇▅▂▂ 4.6   $     off
212   Forest       10.10.10.161   ▂▂▅▆▂▆▇▆▃▃ 4.6   $ #   11 hours
213   Registry     10.10.10.159   ▂▂▄▆▂▆▇▅▃▂ 4.5   $ #   off
```

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
