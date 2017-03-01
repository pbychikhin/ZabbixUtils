

from wmi import WMI
from argparse import ArgumentParser

WMI_IIS_NAMESPACE = "root/WebAdministration"
NOTFOUND_MESSAGE = "notfound"

cmd = ArgumentParser(description="Retrieves the state of a local IIS site using WMI")
cmd.add_argument("-site", help="Site name", required=True)
args = cmd.parse_args()

site_states = dict(enumerate(["starting", "started", "stopping", "stopped", "unknown"]))
sites = WMI(namespace=WMI_IIS_NAMESPACE).query("SELECT * FROM Site WHERE Name = '{}'".format(args.site))
try:
    print(site_states[sites[0].GetState()[0]])
except IndexError:
    print(NOTFOUND_MESSAGE)
