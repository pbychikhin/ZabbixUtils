

import urllib.parse
from wmi import WMI
from argparse import ArgumentParser

ZABBIX_API_PATH = "api_jsonrpc.php"
WMI_IIS_NAMESPACE = "root/WebAdministration"
IIS_PREF_PROTO = "https"

cmd = ArgumentParser(description="Automatically creates Zabbix Web scenarios based on sites in IIS")
cmd.add_argument("hosturl", help="Zabbix's host URL", required=True)
cmd.add_argument("user", help="User name", default="")
cmd.add_argument("password", help="Password", default="")
cmd.add_argument("prefproto", help="Prefer host records having specific proto", default=IIS_PREF_PROTO)
cmd.add_argument("prefhost", help="Prefer host records having specific text in their names", default="")

wmiobj = WMI(namespace=WMI_IIS_NAMESPACE)