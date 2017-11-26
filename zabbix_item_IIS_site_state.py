

import json
import subprocess
import sys
import types
from wmi import WMI
from argparse import ArgumentParser
from ldap3.utils.ciDict import CaseInsensitiveDict as cidict

_FILE_VER = "to_be_filled_by_CI"

WMI_IIS_MONIKER = "root/WebAdministration"
NOTFOUND_MESSAGE = "notfound"
PS_CMD = [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", "Get-Website -Name \"{}\"|Select State|ConvertTo-Json -compress"]

cmd0 = ArgumentParser(add_help=False)
cmd0.add_argument("-version", action="store_true", default=False)
(cmd0_namespace, cmd0_args) = cmd0.parse_known_args()
if cmd0_namespace.version:
    print(_FILE_VER)
    sys.exit()

cmd = ArgumentParser(description="Retrieves the state of a local IIS site using WMI or PS")
cmd.add_argument("-site", help="Site name", required=True)
cmd.add_argument("-method", help="Method of data retrieving", choices=["wmi", "ps"], default="wmi")
cmd.add_argument("-version", help="Print version and exit", action="store_true", default=False)
args = cmd.parse_args(cmd0_args)

if args.method == "wmi":
    site_states = dict(enumerate(["starting", "started", "stopping", "stopped", "unknown"]))
    sites = WMI(moniker=WMI_IIS_MONIKER).query("SELECT * FROM Site WHERE Name = '{}'".format(args.site))
    try:
        print(site_states[sites[0].GetState()[0]], end="")
    except IndexError:
        print(NOTFOUND_MESSAGE)
elif args.method == "ps":
    try:
        PS_CMD[-1] = PS_CMD[-1].format(args.site)
        if sys.version_info.major > 2 and sys.version_info.minor > 4:
            cp = subprocess.run(PS_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        else:
            cp = types.SimpleNamespace()
            cp.stdout = subprocess.check_output(PS_CMD, stderr=subprocess.DEVNULL)
        print(cidict(json.loads(cp.stdout.decode(encoding="ascii"), encoding="ascii"))["state"].lower(),
              end="")
    except json.JSONDecodeError:
        print(NOTFOUND_MESSAGE, end="")
