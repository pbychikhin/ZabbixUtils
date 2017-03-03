

import json
import subprocess
from wmi import WMI
from argparse import ArgumentParser

WMI_IIS_NAMESPACE = "root/WebAdministration"
NOTFOUND_MESSAGE = "notfound"
PS_CMD = [
    "powershell",
   "-NoProfile",
    "-ExecutionPolicy", "Bypass",
   "-Command", "Get-Website -Name \"{}\"|Select State|ConvertTo-Json -compress"]

cmd = ArgumentParser(description="Retrieves the state of a local IIS site using WMI or PS")
cmd.add_argument("-site", help="Site name", required=True)
cmd.add_argument("-method", help="Method of data retrieving", choices=["wmi", "ps"], default="wmi")
args = cmd.parse_args()

if args.method == "wmi":
    site_states = dict(enumerate(["starting", "started", "stopping", "stopped", "unknown"]))
    sites = WMI(namespace=WMI_IIS_NAMESPACE).query("SELECT * FROM Site WHERE Name = '{}'".format(args.site))
    try:
        print(site_states[sites[0].GetState()[0]], end="")
    except IndexError:
        print(NOTFOUND_MESSAGE)
elif args.method == "ps":
    try:
        PS_CMD[-1] = PS_CMD[-1].format(args.site)
        cp = subprocess.run(PS_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        print(json.loads(cp.stdout.decode(encoding="ascii"), encoding="ascii")["state"].lower(), end="")
    except json.JSONDecodeError:
        print(NOTFOUND_MESSAGE, end="")
