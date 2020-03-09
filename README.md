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

## Example Usage

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

# Grab the mango box and start it
mango = [m for m in cnxn.machines if m.name == "Mango"]
mango.spawned = True

# Cancel all machine resets (probably shouldn't do this...)
for m in filter(lambda m: m.resetting, cnxn.machines):
	m.resetting = False
```
