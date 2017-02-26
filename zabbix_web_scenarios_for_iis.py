

import urllib.parse
import re
from wmi import WMI
from argparse import ArgumentParser

ZABBIX_API_PATH = "api_jsonrpc.php"
WMI_IIS_NAMESPACE = "root/WebAdministration"
IIS_PREF_PROTO = "https"

cmd = ArgumentParser(description="Automatically creates Zabbix Web scenarios based on sites in IIS")
cmd.add_argument("-hosturl", help="Zabbix's host URL", required=True)
cmd.add_argument("-user", help="User name", default="")
cmd.add_argument("-password", help="Password", default="")
cmd.add_argument("-prefproto", help="Prefer host records having specific proto", default=IIS_PREF_PROTO)
cmd.add_argument("-prefhost", help="Prefer host records having specific text in their names", default=None)
args = cmd.parse_args()


class IIS_binding_info:
    def __init__(self, site_instance, prefproto=IIS_PREF_PROTO, prefhost=args.prefhost):
        self.name = site_instance.Name
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
    def get_bindings(self):
        return self.bindings
    def get_pref_binding(self):
        return self.pref_binding

wmiobj = WMI(namespace=WMI_IIS_NAMESPACE)
sites = [IIS_binding_info(site) for site in wmiobj.instances("Site")]
for site in sites:
    print(site.get_name())
    print("{}protocol: {}".format(" "*3, site.get_pref_binding()["proto"]))
    print("{}host: {}".format(" "*3, site.get_pref_binding()["host"]))
    print("{}port: {}".format(" "*3, site.get_pref_binding()["port"]))
    print("{}addr: {}".format(" "*3, site.get_pref_binding()["addr"]))
