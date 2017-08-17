

import json
import re
import types
import subprocess
import sys
from wmi import WMI
from argparse import ArgumentParser
from ldap3.utils.ciDict import CaseInsensitiveDict as cidict

FILE_VER = "to_be_filled_by_CI"

WMI_IIS_MONIKER = "root/WebAdministration"
IIS_PREF_PROTO = "https"
PS_CMD = [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command", "Get-Website|Select Name,Bindings,ServerAutoStart|ConvertTo-Json -depth 3 -compress"]

cmd = ArgumentParser(description="Discovers sites in local IIS using WMI or PS")
cmd.add_argument("-prefproto", help="Prefer host records having specific proto. Default is {}".format(IIS_PREF_PROTO), default=IIS_PREF_PROTO)
cmd.add_argument("-prefhost", help="Prefer host records having specific text in their names", default=None)
cmd.add_argument("-method", help="Method of data retrieving", choices=["wmi", "ps"], default="wmi")
cmd.add_argument("-version", help="Print version and exit", action="store_true", default=False)
args = cmd.parse_args()

if args.version:
    print(FILE_VER)
    sys.exit()


class IIS_site_info:
    site_startup_type = {True: "auto", False: "manual"}

    def __init__(self, site_instance, prefproto=IIS_PREF_PROTO, prefhost=args.prefhost):
        self.name = site_instance.Name
        self.autostart = site_instance.ServerAutoStart
        self.bindings = []
        self.pref_binding = None
        pref_binding_found_both = False
        pref_binding_found_host = False
        for b in site_instance.Bindings:
            binding = dict(zip(["addr", "port", "host"], b.BindingInformation.split(":")), proto=b.protocol)
            found_host, found_proto = False, False
            if prefhost and re.search(re.escape(prefhost), binding["host"], re.I):
                found_host = True
            if re.search("^{}$".format(prefproto), binding["proto"], re.I):
                found_proto = True
            if not pref_binding_found_both and found_host and found_proto:
                self.pref_binding = binding
                pref_binding_found_both = True
            else:
                if found_host:
                    self.pref_binding = binding
                    pref_binding_found_host = True
                elif not pref_binding_found_host and found_proto:
                    self.pref_binding = binding
            self.bindings.append(binding)
        if self.pref_binding is None:
            self.pref_binding = self.bindings[-1]

    def get_name(self):
        return self.name

    def get_startuptype(self):
        return type(self).site_startup_type[self.autostart]

    def get_bindings(self):
        return self.bindings

    def get_pref_binding(self):
        return self.pref_binding


class IIS_site_info_json(IIS_site_info):

    def __init__(self, site_instance_json, prefproto=IIS_PREF_PROTO, prefhost=args.prefhost):
        site_instance = types.SimpleNamespace()
        site_instance.Name = site_instance_json["name"]
        site_instance.ServerAutoStart = bool(site_instance_json["serverAutoStart"])
        site_instance.Bindings = []
        for b in site_instance_json["bindings"]["Collection"]:
            binding = types.SimpleNamespace()
            binding.protocol = b["protocol"]
            binding.BindingInformation = b["bindingInformation"]
            site_instance.Bindings.append(binding)
        IIS_site_info.__init__(self, site_instance, prefproto, prefhost)

sites = []
if args.method == "wmi":
    sites = [IIS_site_info(site) for site in WMI(moniker=WMI_IIS_MONIKER).query("SELECT * FROM Site")]
elif args.method == "ps":
    if sys.version_info.major > 2 and sys.version_info.minor > 4:
        cp = subprocess.run(PS_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    else:
        cp = types.SimpleNamespace()
        cp.stdout = subprocess.check_output(PS_CMD, stderr=subprocess.DEVNULL)
    try:
        sites = [IIS_site_info_json(cidict(site)) for site in json.loads(cp.stdout.decode(encoding="ascii"), encoding="ascii")]
    except json.JSONDecodeError:
        sites = []
zabbix_data = {"data": [{
        "{#SITE_NAME}": site.get_name(),
        "{#SITE_START}": site.get_startuptype(),
        "{#SITE_PROTO}": site.get_pref_binding()["proto"],
        "{#SITE_HOST}": site.get_pref_binding()["host"],
        "{#SITE_ALL_HOSTS}": ",".join(sorted(set([x["host"] for x in site.get_bindings()]))),
        "{#SITE_PORT}": site.get_pref_binding()["port"],
        "{#SITE_ADDR}": site.get_pref_binding()["addr"]}
                        for site in sites]}
print(json.dumps(zabbix_data), end="")
