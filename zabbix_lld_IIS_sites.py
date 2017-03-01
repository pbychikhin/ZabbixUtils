

import json
import re
from wmi import WMI
from argparse import ArgumentParser

WMI_IIS_NAMESPACE = "root/WebAdministration"
IIS_PREF_PROTO = "https"

cmd = ArgumentParser(description="Discovers sites in local IIS using WMI")
cmd.add_argument("-prefproto", help="Prefer host records having specific proto", default=IIS_PREF_PROTO)
cmd.add_argument("-prefhost", help="Prefer host records having specific text in their names", default=None)
args = cmd.parse_args()


class IIS_site_info:
    site_startup_type = {True: "auto", False: "noauto"}

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


sites = [IIS_site_info(site) for site in WMI(namespace=WMI_IIS_NAMESPACE).instances("Site")]
zabbix_data = {"data": [{
        "{#SITE_NAME}": site.get_name(),
        "{#SITE_START}": site.get_startuptype(),
        "{#SITE_PROTO}": site.get_pref_binding()["proto"],
        "{#SITE_HOST}": site.get_pref_binding()["host"],
        "{#SITE_PORT}": site.get_pref_binding()["port"],
        "{#SITE_ADDR}": site.get_pref_binding()["addr"]}
                        for site in sites]}
print(json.dumps(zabbix_data))
