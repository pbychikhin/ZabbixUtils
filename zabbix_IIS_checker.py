
import queue
import pyzabbix
import types
import itertools
import re
import time
import random
import wmi
import sys
import os.path
import subprocess
import json
import urllib.parse
import configparser
import pycurl
import io
import cgi
import threading
import concurrent.futures
import logging
import math
import argparse
import win32api
import win32con
import win32service
import win32serviceutil
from ldap3.utils.ciDict import CaseInsensitiveDict as cidict
from sys import exit

_FILE_VER = "to_be_filled_by_CI"

_IIS_PREF_PROTO = "https"
_WMI_IIS_MONIKER = "root/WebAdministration"
_RETRY_TIMERS = [math.exp(x/10) for x in range(0, 25, 5)] + [0]


class Utils:

    _U_HOSTLIST_SEPARATOR = ","

    @staticmethod
    def validate_value(var, allowed, description):
        if var not in allowed:
            raise ValueError("Invalid {}: {}. Valid ones are: {}"
                             .format(description, var, ", ".join(allowed)))

    @staticmethod
    def make_filename(path, argv_0=sys.argv[0]):
        """
        :param path: Relative to app's dir of full file path
        :param argv_0: Path to script. When a script is running as a service, sys.argv[0] doesn't point to it. So it needs to be specified explicitly
        :return: Full file path
        """
        mydir = os.path.dirname(argv_0)
        parts = os.path.split(path)
        if len(parts[0]) == 0 and len(parts[1]) > 0:
            return os.path.join(mydir, parts[1])
        else:
            return path

    @property
    def _hostlist_separator(self):
        return type(self)._U_HOSTLIST_SEPARATOR


class Message:

    _MSG_PROCESS_DATA = 0x1
    _MSG_STOP_EXECUTION = 0x2
    _MSG_REGISTER_CLIENT = 0x4
    _MSG_DEREGISTER_CLIENT = 0x8
    _MSG_FORCE_STOP_EXECUTION = 0x10

    def __init__(self):
        self._msg_type = 0x0
        self._msg_data = None

    def send_process_data(self, data):
        self._msg_type = type(self)._MSG_PROCESS_DATA
        if isinstance(data, list):
            self._msg_data = data
        else:
            self._msg_data = [data]
        return self

    @property
    def process_data(self):
        if self._msg_type & type(self)._MSG_PROCESS_DATA:
            return [True, self._msg_data]
        else:
            return [False, None]

    def send_stop_execution(self, data=None):
        self._msg_type = type(self)._MSG_STOP_EXECUTION
        self._msg_data = data
        return self

    @property
    def stop_execution(self):
        if self._msg_type & type(self)._MSG_STOP_EXECUTION:
            return [True, None]
        else:
            return [False, None]

    def send_register_client(self, data):
        self._msg_type = type(self)._MSG_REGISTER_CLIENT
        self._msg_data = data
        return self

    @property
    def register_client(self):
        if self._msg_type & type(self)._MSG_REGISTER_CLIENT:
            return [True, self._msg_data]
        else:
            return [False, None]

    def send_deregister_client(self, data):
        self._msg_type = type(self)._MSG_DEREGISTER_CLIENT
        self._msg_data = data
        return self

    @property
    def deregister_client(self):
        if self._msg_type & type(self)._MSG_DEREGISTER_CLIENT:
            return [True, self._msg_data]
        else:
            return [False, None]

    def send_force_stop_execution(self, data=None):
        self._msg_type = type(self)._MSG_FORCE_STOP_EXECUTION
        self._msg_data = data
        return self

    @property
    def force_stop_execution(self):
        if self._msg_type & type(self)._MSG_FORCE_STOP_EXECUTION:
            return [True, None]
        else:
            return [False, None]


class Sender(Utils):

    _allowed_types = {"print", "send"}

    def __init__(self, q, sender_type="print", zbx_srv="127.0.0.1", zbx_port=10051, zbx_host=None):
        self.validate_value(sender_type, type(self)._allowed_types, "sender type")
        self.sender_type = sender_type
        self.q = q
        self.zbx_srv = zbx_srv
        self.zbx_port = zbx_port
        self.zbx_host = zbx_host

    def run(self):
        clients = set()
        stop = False
        while True:
            if not stop or clients:
                msg = self.q.get()
            else:
                try:
                    msg = self.q.get_nowait()
                except queue.Empty:
                    break
            if msg.process_data[0]:
                if self.sender_type == "print":
                    for data in msg.process_data[1]:
                        if len(data) == 4 and isinstance(data[3], io.BytesIO):
                            print(data[0:3])
                            print(data[3].getvalue().decode("ASCII", errors="ignore"))  # "ignore" might not be the best handler
                        else:
                            print(data)
                elif self.sender_type == "send":
                    zbx_packet = list()
                    for data in msg.process_data[1]:
                        zbx_packet.append(pyzabbix.ZabbixMetric(self.zbx_host, data[1], data[2]))  # data[1] is Zabbis key and data[2] is Zabbix value,
                                                                                                   # data[0] is an IIS site name and data[3] is optional info (verbose Curl output)
                    pyzabbix.ZabbixSender(self.zbx_srv, self.zbx_port).send(zbx_packet)
            elif msg.register_client[0]:
                clients.add(msg.register_client[1])
            elif msg.deregister_client[0]:
                try:
                    clients.remove(msg.deregister_client[1])
                except KeyError:
                    pass
            elif msg.stop_execution[0]:
                stop = True
            elif msg.force_stop_execution[0]:
                break


class IIS_site_info:

    site_startup_type = {True: "auto", False: "manual"}

    def __init__(self, site_instance, prefproto=_IIS_PREF_PROTO, prefhost=None):
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

    def get_normalised_hostnames(self):
        return sorted(set([x["host"] for x in self.bindings]))

    def get_pref_binding(self):
        return self.pref_binding


class IIS_site_info_json(IIS_site_info):

    def __init__(self, site_instance_json, prefproto=_IIS_PREF_PROTO, prefhost=None):
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


class WrappedList:  # This class is used to define IIS_sites (see below)

    def __init__(self):
        self._items = list()

    def reset(self):
        self._items = list()

    def add(self, site):
        self._items.append(site)

    def get(self):
        return self._items


class Discoverer(Utils):

    _allowed_methods = {"wmi", "ps"}

    def __init__(self, q, evt_discovery_done, IIS_sites, cache_time=900, method="ps",
                 prefproto=_IIS_PREF_PROTO, prefhost=None):
        self.validate_value(method, type(self)._allowed_methods, "discovery method")
        self._q = q
        self._evt_discovery_done = evt_discovery_done
        self._IIS_sites = IIS_sites
        self._cache_time = cache_time
        self._method = method
        self._prefproto = prefproto
        self._prefhost = prefhost

    def run(self):
        wmi_iis_moniker = _WMI_IIS_MONIKER
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", "Get-Website|Select Name,Bindings,ServerAutoStart|ConvertTo-Json -depth 3 -compress"]
        last_discovery_time = 0
        while True:
            msg = self._q.get()
            if msg.process_data[0]:
                try:
                    if time.time() - last_discovery_time > self._cache_time:
                        self._IIS_sites.reset()
                        logging.info("Performing discovery using {} method".format(self._method))
                        if self._method == "wmi":
                            good = False
                            retry_counter = 0
                            for retry_timer in _RETRY_TIMERS:
                                try:
                                    for site in wmi.WMI(moniker=wmi_iis_moniker).query("SELECT * FROM Site"):
                                        self._IIS_sites.add(IIS_site_info(site, self._prefproto, self._prefhost))
                                except Exception as exc:
                                    retry_counter += 1
                                    if retry_counter <= len(_RETRY_TIMERS):
                                        logging.warning("Could not perform discovery due to {}. Re-trying in {:.2f} seconds".format(exc, retry_timer))
                                        time.sleep(retry_timer)
                                    else:
                                        logging.error("Could not perform discovery after {} tries. Giving up".format(max(0, retry_counter - 1)))
                                else:
                                    good = True
                                    break
                            if not good:
                                logging.critical("Could not perform discovery due to errors. Shutting down")
                                break
                        elif self._method == "ps":
                            if sys.version_info.major > 2 and sys.version_info.minor > 4:
                                cp = subprocess.run(ps_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                            else:
                                cp = types.SimpleNamespace()
                                cp.stdout = subprocess.check_output(ps_cmd, stderr=subprocess.DEVNULL)
                            try:
                                for site in json.loads(cp.stdout.decode(encoding="ascii"), encoding="ascii"):
                                    self._IIS_sites.add(IIS_site_info_json(cidict(site), self._prefproto, self._prefhost))
                            except json.JSONDecodeError:
                                pass
                                # TODO: We consider json errors as transient,
                                # TODO: but it would be great to add some logging here
                        last_discovery_time = time.time()
                    else:
                        logging.info("Using cached data")
                finally:
                    self._evt_discovery_done.set()  # We must set event in any case. Infinite waiting will occur otherwise
            elif msg.stop_execution[0]:
                break
            elif msg.force_stop_execution[0]:
                break


class Checker(Utils):


    class _Website:

        well_known_ports = cidict({"http": "80", "https": "443"})

        def __init__(self, scheme="http", host="localhost", port="80", addr="127.0.0.1",
                     path='[{"path": "/", "body": null}]'):
            if not re.search("^(http|https)$", scheme, re.I):
                raise RuntimeError("Unknown scheme {}".format(scheme))
            self.scheme = scheme
            self.host = "localhost" if host == "" else host
            self.addr = "127.0.0.1" if addr == "*" else addr
            self.port = port if port is not None else type(self).well_known_ports[scheme]
            path = json.loads(path)
            self.url = []
            for p in path:
                if "path" in p:
                    p["path"] = urllib.parse.urlunparse(
                        urllib.parse.ParseResult(self.scheme, ":".join([self.host, self.port]), p["path"], "", "", ""))
                else:
                    p["path"] = urllib.parse.urlunparse(
                        urllib.parse.ParseResult(self.scheme, ":".join([self.host, self.port]), "/", "", "", ""))
                if "body" not in p:
                    p["body"] = None
                if "nobody" not in p:
                    p["nobody"] = None
                self.url.append(p)
            self.curl_resolved_host = ":".join([self.host, self.port, self.addr]) if self.addr is not None else None

        def get_url(self):
            return self.url

        def get_curl_host(self):
            return self.curl_resolved_host


    class _Config:

        def __init__(self, iniobj, skipsections=set()):
            """
            :param iniobj: a parsed ini-file object
            :param skipsections: a set of section names that are irrelevant to the Checker and have to be skipped
            """
            self._defaults = types.SimpleNamespace()
            self._defaults.scheme = "http"     # TODO: seems useless, try to remove
            self._defaults.host = "localhost"  # TODO: seems useless, try to remove
            self._defaults.port = None         # TODO: seems useless, try to remove
            self._defaults.addr = None         # TODO: seems useless, try to remove
            self._defaults.path = '[{"path": "/", "body": null}]'
            self._defaults.timeout = 300
            self._defaults.delay = 30
            self._defaults.nameservers = None
            self._defaults.v4 = False
            self._defaults.v6 = False
            # TODO: ca is the subject for processing with Utils.make_filename
            self._defaults.ca = None  # CA bundle (file name)
            self._defaults.verbose = False  # make Curl verbose and log its output
            self._sites = dict()
            for section in iniobj.sections():
                if section in skipsections:
                    continue
                elif section == "_defaulthost":
                    host = self._defaults
                else:
                    try:
                        site_key = frozenset([x.strip().lower() for x in
                                              re.split("\s*,\s*", iniobj.get(section, "allhosts"))])
                        if site_key not in self._sites:
                            self._sites[site_key] = types.SimpleNamespace()
                        host = self._sites[site_key]
                    except configparser.NoOptionError:
                        continue
                for option in iniobj.options(section):
                    if option == "allhosts":
                        continue
                    elif option in {"timeout", "delay"}:
                        o_value = iniobj.getint(section, option)
                        if o_value < 0:
                            raise ValueError("{}.{} should be a non-negative integer".format(section, option))
                        setattr(host, option, iniobj.getint(section, option))
                    elif option in {"v4", "v6", "verbose"}:
                        setattr(host, option, iniobj.getboolean(section, option))
                    else:
                        setattr(host, option, iniobj.get(section, option))

        def get(self, allhosts):
            """
            :param allhosts: a set of host names bound to an IIS site
            :return: a namespace with site specific or default parameters
            """
            site = self._defaults
            for key in self._sites.keys():
                if key & allhosts:
                    site = self._sites[key]
                    break
            rv = types.SimpleNamespace()
            for var in vars(self._defaults):
                try:
                    setattr(rv, var, getattr(site, var))
                except (KeyError, AttributeError):
                    setattr(rv, var, getattr(self._defaults, var))
            return rv


    def get_site_state(self, name, method):
        """
        :param name: IIS site name
        :param method: a method of fetching data about IIS, may be "wmi" or "ps"
        :return: a tuple: (IIS site name, Zabbix key, IIS site state)
        """
        ZBX_KEY_PREFIX = "iis.site.state"
        wmi_iis_moniker = _WMI_IIS_MONIKER
        notfound = "notfound"
        zbx_key = "{}[{}]".format(ZBX_KEY_PREFIX, name)
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", "Get-Website -Name \"{}\"|Select State|ConvertTo-Json -compress"]
        siteconfig = self._cfg.get({name.lower()})
        time.sleep(random.randint(0, siteconfig.delay))
        logging.debug("Getting site state using {} method".format(method))
        if method == "wmi":
            site_states = dict(enumerate(["starting", "started", "stopping", "stopped", "unknown"]))
            good = False
            retry_counter = 0
            rt_exc = None
            for retry_timer in _RETRY_TIMERS:
                try:
                    sites = wmi.WMI(moniker=wmi_iis_moniker).query("SELECT * FROM Site WHERE Name = '{}'".format(name))
                except Exception as exc:
                    retry_counter += 1
                    if retry_counter < len(_RETRY_TIMERS):
                        logging.warning("Could not get site state due to {}. Re-trying in {:.2f} seconds".format(exc, retry_timer))
                        time.sleep(retry_timer)
                    else:
                        logging.error("Could not get site state after {} tries. Giving up".format(max(0, retry_counter - 1)))
                        rt_exc = exc
                else:
                    good = True
                    break
            if not good:
                logging.error("Could not get site state due to errors. Return value has the exception object instead of site state")
                return name, zbx_key, rt_exc
            try:
                return name, zbx_key, site_states[sites[0].GetState()[0]]
            except IndexError:
                return name, zbx_key, notfound
        elif method == "ps":
            try:
                ps_cmd[-1] = ps_cmd[-1].format(name)
                if sys.version_info.major > 2 and sys.version_info.minor > 4:
                    cp = subprocess.run(ps_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                else:
                    cp = types.SimpleNamespace()
                    cp.stdout = subprocess.check_output(ps_cmd, stderr=subprocess.DEVNULL)
                return name, zbx_key, cidict(json.loads(cp.stdout.decode(encoding="ascii"), encoding="ascii"))["state"].lower()
            except json.JSONDecodeError:
                return name, zbx_key, notfound
        else:
            return name, zbx_key, notfound

    def get_site_probe(self, siteobj):
        """
        :param siteobj: an instance of IIS_site_info
        :return: a tuple: (IIS site name, Zabbix key, IIS site probe status, Buffer with verbose output (might be None if verbosity is not requested))
        """
        ZBX_KEY_PREFIX = "iis.site.probe"
        OK_MESSAGE = "STATUS_OK"
        CURL_TIMEOUT_MESSAGE = "STATUS_ERR_TIMEOUT"
        CURL_FAILED_MESSAGE = "STATUS_ERR_FAILED"
        WEBSITE_FAILED_MESSAGE = "STATUS_ERR_WEBAPP_PROBLEM"
        HTML_DEFAULT_CHARSET = "UTF-8"
        HTML_FALLBACK_CHARSET = "ISO-8859-1"
        sitebindings = self._hostlist_separator.join(siteobj.get_normalised_hostnames())
        if self._hostlist_separator in sitebindings:
            zbx_key_pattern = "{}[{},{},{},{},\"{}\"]"
        else:
            zbx_key_pattern = "{}[{},{},{},{},{}]"
        zbx_key = zbx_key_pattern.format(ZBX_KEY_PREFIX,
                                         siteobj.get_pref_binding()["proto"],
                                         siteobj.get_pref_binding()["host"],
                                         siteobj.get_pref_binding()["port"],
                                         siteobj.get_pref_binding()["addr"],
                                         sitebindings)
        siteconfig = self._cfg.get(set([x["host"].lower() for x in siteobj.get_bindings()]))
        time.sleep(random.randint(0, siteconfig.delay))
        w = self._Website(
            scheme=siteobj.get_pref_binding()["proto"],
            host=siteobj.get_pref_binding()["host"],
            port=siteobj.get_pref_binding()["port"],
            addr=siteobj.get_pref_binding()["addr"],
            path=siteconfig.path
        )
        c = pycurl.Curl()
        if siteconfig.v4 ^ siteconfig.v6:
            if siteconfig.v4:
                c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V4)
            elif siteconfig.v6:
                c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V6)
        else:
            c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_WHATEVER)
        if siteconfig.nameservers:
            c.setopt(pycurl.DNS_SERVERS, siteconfig.nameservers)
        if w.get_curl_host() is not None:
            c.setopt(pycurl.RESOLVE, [w.get_curl_host()])
        if siteconfig.ca is not None:
            c.setopt(pycurl.CAINFO, siteconfig.ca)
        c.setopt(pycurl.TIMEOUT, siteconfig.timeout)
        curl_debug_buf = None
        if siteconfig.verbose:
            curl_debug_buf = io.BytesIO()

            def curl_debugfunction(debugtype, debugbytes, buf=curl_debug_buf):
                if debugtype in (pycurl.INFOTYPE_TEXT, pycurl.INFOTYPE_HEADER_IN, pycurl.INFOTYPE_HEADER_OUT):
                    buf.write(debugbytes)

            c.setopt(pycurl.VERBOSE, siteconfig.verbose)
            c.setopt(pycurl.DEBUGFUNCTION, curl_debugfunction)
        for url in w.get_url():
            buffer = io.BytesIO()
            c.setopt(pycurl.WRITEDATA, buffer)
            c.setopt(pycurl.URL, url["path"])
            try:
                c.perform()
            except pycurl.error as curl_error:
                if curl_error.args[0] == pycurl.E_OPERATION_TIMEDOUT:
                    return siteobj.get_name(), zbx_key, CURL_TIMEOUT_MESSAGE, curl_debug_buf
                else:
                    return siteobj.get_name(), zbx_key, CURL_FAILED_MESSAGE, curl_debug_buf
            else:
                response_info = {"code": c.getinfo(pycurl.RESPONSE_CODE),
                                 "type": c.getinfo(pycurl.CONTENT_TYPE)}
                ct_params = cidict(cgi.parse_header(response_info["type"])[1]) if response_info["type"] is not None else cidict()
                response_info["charset"] = ct_params["charset"] if "charset" in ct_params else HTML_DEFAULT_CHARSET
            finally:
                c.close()
            if response_info["code"] >= 400:
                return siteobj.get_name(), zbx_key, WEBSITE_FAILED_MESSAGE, curl_debug_buf
            try:
                body = buffer.getvalue().decode(response_info["charset"])
            except UnicodeDecodeError:
                try:
                    body = buffer.getvalue().decode(HTML_FALLBACK_CHARSET)
                except ValueError:
                    return siteobj.get_name(), zbx_key, WEBSITE_FAILED_MESSAGE, curl_debug_buf
            if url["body"] and not re.search(url["body"], body, re.I):
                return siteobj.get_name(), zbx_key, WEBSITE_FAILED_MESSAGE, curl_debug_buf
            elif url["nobody"] and re.search(url["nobody"], body, re.I):
                return siteobj.get_name(), zbx_key, WEBSITE_FAILED_MESSAGE, curl_debug_buf
        return siteobj.get_name(), zbx_key, OK_MESSAGE, curl_debug_buf

    _allowed_methods = {"wmi", "ps"}

    def __init__(self, q, sq, dq, evt_discovery_done, IIS_sites, iniobj, method="ps"):
        """
        :param q: command queue
        :param sq: Sender's command queue
        :param dq: Discoverer's command queue
        :param evt_discovery_done: the event being sent by Discoverer
        :param IIS_sites: a WrappedList's instance holding a list of IIS sites filled by Discoverer
        :param iniobj: a parsed ini-file object
        :param method: a method of fetching data about IIS, may be "wmi" or "ps"
        """
        self.validate_value(method, type(self)._allowed_methods, "getting state method")
        self._q = q
        self._sq = sq
        self._dq = dq
        self._evt_discovery_done = evt_discovery_done
        self._IIS_sites = IIS_sites
        self._cfg = self._Config(iniobj, {"_appglobal"})
        self._method = method

    def run(self):
        self._sq.put_nowait(Message().send_register_client(threading.current_thread().name))
        while True:
            msg = self._q.get()
            if msg.process_data[0]:
                self._evt_discovery_done.clear()
                self._dq.put_nowait(Message().send_process_data(None))
                self._evt_discovery_done.wait()
                if len(self._IIS_sites.get()) > 0:
                    logging.info("Fetching sites states")
                    data_to_send = list()
                    sites_started = set()
                    good = True
                    with concurrent.futures.ThreadPoolExecutor(max_workers=len(self._IIS_sites.get())) as executor:
                        for state_info in executor.map(self.get_site_state,
                                                       (site.get_name() for site in self._IIS_sites.get()),
                                                       itertools.repeat(self._method, len(self._IIS_sites.get()))):
                            if isinstance(state_info[2], Exception):
                                logging.critical("Could not fetch the state of {} due to {}. Shutting down".format(state_info[0], state_info[2]))
                                good = False
                                break
                            data_to_send.append(state_info)
                            if state_info[2] == "started":
                                sites_started.add(state_info[0])
                    if not good:
                        break
                    self._sq.put_nowait(Message().send_process_data(data_to_send))
                    if len(sites_started) > 0:
                        logging.info("Probing sites")
                        time.sleep(5)  # give some time for dust to settle
                        data_to_send = list()
                        with concurrent.futures.ThreadPoolExecutor(max_workers=len(sites_started)) as executor:
                            for probe_info in executor.map(self.get_site_probe, (site for site in self._IIS_sites.get() if site.get_name() in sites_started)):
                                data_to_send.append(probe_info)
                        self._sq.put_nowait(Message().send_process_data(data_to_send))
            elif msg.stop_execution[0]:
                self._sq.put_nowait(Message().send_deregister_client(threading.current_thread().name))
                break
            elif msg.force_stop_execution[0]:
                break


class CheckerService(win32serviceutil.ServiceFramework, Utils):

    _svc_name_ = "zabbix_iis_checker"
    _svc_display_name_ = "Zabbix IIS checker"
    _svc_description_ = "Checks IIS sites and sends the results over to Zabbix server"

    _ALLOWED_MODES = {"standalone", "service", "discovery"}
    _MODE_STANDALONE = "standalone"
    _MODE_SERVICE = "service"
    _MODE_DISCOVERY = "discovery"
    _DEFAULT_INTERVAL = 300
    _THREADSET_CHECK_INTERVAL = 15
    _REG_KEY = win32con.HKEY_LOCAL_MACHINE
    _REG_KEY_NAME = "HKEY_LOCAL_MACHINE"
    _REG_SUBKEY = "SOFTWARE\\Zabbix User Tools\\IIS Checker"
    _REG_VALUE_NAME = "argv_0"

    def __init__(self, args, mode="service", configfile=None):
        """
        :param args: win32serviceutil.ServiceFramework.__init__(self, args)
        :param mode: instantiation mode. can be one of "standalone", "service", "discover"
        :param configfile: path to config file if script runs in standalone mode
        """
        if mode == "service":
            win32serviceutil.ServiceFramework.__init__(self, args)

        self.validate_value(mode, type(self)._ALLOWED_MODES, "instantiation mode")
        self.mode = mode
        if self.mode == "service":  # find the path to script (argv[0]). if runs as a service, the script can only get it from registry
            try:
                hk = win32api.RegOpenKeyEx(type(self)._REG_KEY, type(self)._REG_SUBKEY)
            except Exception:
                logging.critical("Could not open registry key \"{}\{}\"".format(type(self)._REG_KEY_NAME, type(self)._REG_SUBKEY), exc_info=True)
                exit(1)
            else:
                try:
                    self.argv_0 = win32api.RegQueryValueEx(hk, type(self)._REG_VALUE_NAME)[0]
                except Exception:
                    logging.critical("Could not get registry value \"{}\": ".format(type(self)._REG_VALUE_NAME), exc_info=True)
                    exit(1)
        else:
            self.argv_0 = sys.argv[0]

        self.cfg = configparser.ConfigParser()
        try:  # find config file if possible. if not found, the defaults will be used
            if configfile is None:
                configfile = ".".join([os.path.basename(self.argv_0).split(".")[0], "ini"])
            configfile = self.make_filename(configfile, self.argv_0)
            self.cfg.read_file(open(configfile))
        except FileNotFoundError:
            pass
        except OSError:
            logging.critical("Could not read config file", exc_info=True)
            exit(1)
        except configparser.Error:
            logging.critical("Could not parse config file", exc_info=True)
            exit(1)

        self.interval = self.cfg.getint(section="_appglobal", option="interval", fallback=type(self._DEFAULT_INTERVAL))  # IIS checking interval

        log_params = dict()  # logging module parameters
        if self.cfg.has_option(section="_appglobal", option="logfile"):
            log_params["filename"] = self.make_filename(self.cfg.get(section="_appglobal", option="logfile"), self.argv_0)
        if self.cfg.has_option(section="_appglobal", option="loglevel"):
            log_params["level"] = getattr(logging, self.cfg.get(section="_appglobal", option="loglevel").upper())
        logging.basicConfig(
            format="{asctime} [{threadName}] [{levelname}] {message}",
            style="{",
            filemode="w",
            **log_params)

        logging.info("Initializing")

        self.discoverer_params = dict()
        if self.cfg.has_option("_appglobal", "discovery_method"):
            self.discoverer_params["method"] = self.cfg.get("_appglobal", "discovery_method")
        if self.cfg.has_option("_appglobal", "discovery_prefproto"):
            self.discoverer_params["prefproto"] = self.cfg.get("_appglobal", "discovery_prefproto")
        if self.cfg.has_option("_appglobal", "discovery_prefhost"):
            self.discoverer_params["prefhost"] = self.cfg.get("_appglobal", "discovery_prefhost")

        self.sender_params = dict()
        if self.cfg.has_option("_appglobal", "sender_type"):
            self.sender_params["sender_type"] = self.cfg.get("_appglobal", "sender_type")
        if self.cfg.has_option("_appglobal", "zbx_srv"):
            self.sender_params["zbx_srv"] = self.cfg.get("_appglobal", "zbx_srv")
        if self.cfg.has_option("_appglobal", "zbx_port"):
            self.sender_params["zbx_port"] = self.cfg.getint("_appglobal", "zbx_port")
        if self.cfg.has_option("_appglobal", "zbx_host"):
            self.sender_params["zbx_host"] = self.cfg.get("_appglobal", "zbx_host")

        self.checker_params = dict()
        if self.cfg.has_option("_appglobal", "check_method"):
            self.checker_params["method"] = self.cfg.get("_appglobal", "check_method")

        self.qsender = queue.Queue()  # Sender's queue
        self.qdiscoverer = queue.Queue()  # Discoverer's queue
        self.qchecker = queue.Queue()  # Checker's queue
        self.ediscovery = threading.Event()  # "Discovery done" event
        self.estop = threading.Event() # "Application stop" event
        self.sites = WrappedList()  # IIS sites discovered
        threading.Thread(target=self._shutdown, name="Shutdowner").start()  # Control is sent to this thread from SvcStop to ensure fast response to service manager
        self.shutdown_init = False  # Whether the shutdown process has been initiated
        self.init_threadset = set(t.name for t in threading.enumerate())  # Set of threads at the begginnig. We are not supposed to kill them

    def _get_died_threadset(self):
        logging.debug("Init threadset: {}".format(self.init_threadset))
        logging.debug("Current threadset: {}".format(set(t.name for t in threading.enumerate())))
        logging.debug("Expected threadset: {}".format(self.expected_threadset))
        return self.expected_threadset - self.init_threadset - (set(t.name for t in threading.enumerate()) & self.expected_threadset)

    def _shutdown(self):
        self.estop.wait()
        logging.warning("Shutting down")
        died_threadset = self._get_died_threadset()
        for q in self.shutdown_sequence:
            if q[1].name not in died_threadset:
                if len(died_threadset) > 0:
                    q[0].put_nowait(Message().send_force_stop_execution())
                else:
                    q[0].put_nowait(Message().send_stop_execution())
                logging.info("Waiting for {} to shut down".format(q[1].name))
                q[1].join()

    def _startup(self):
        logging.warning("Starting up in {} mode".format(self.mode))

        self.expected_threadset = self.init_threadset | set()
        self.shutdown_sequence = list()

        self.tdiscoverer = threading.Thread(target=Discoverer(q=self.qdiscoverer, evt_discovery_done=self.ediscovery, IIS_sites=self.sites,
                                                              **self.discoverer_params).run, name="Discoverer")
        self.tdiscoverer.start()
        self.expected_threadset = self.expected_threadset | {self.tdiscoverer.name}
        self.shutdown_sequence.append((self.qdiscoverer, self.tdiscoverer))

        if (self.mode in {type(self)._MODE_STANDALONE, type(self)._MODE_SERVICE}):
            self.tsender = threading.Thread(target=Sender(q=self.qsender, **self.sender_params).run, name="Sender")
            self.tsender.start()
            self.tchecker = threading.Thread(target=Checker(q=self.qchecker,
                                                            sq=self.qsender,
                                                            dq=self.qdiscoverer,
                                                            evt_discovery_done=self.ediscovery,
                                                            IIS_sites=self.sites,
                                                            iniobj=self.cfg,
                                                            **self.checker_params).run, name="Checker")
            self.tchecker.start()
            self.expected_threadset = self.expected_threadset | {t.name for t in (self.tsender, self.tchecker)}
            self.shutdown_sequence.extend([(self.qsender, self.tsender), (self.qchecker, self.tchecker)])

        self.shutdown_sequence.reverse()

    def _run_checker(self):
        time_slept = max(self.interval - type(self)._THREADSET_CHECK_INTERVAL, type(self)._THREADSET_CHECK_INTERVAL)
        stop = False
        while True:
            while time_slept < self.interval:
                if self.shutdown_init:
                    logging.debug("Shutdown initiated. Breaking the checker loop")
                    stop = True
                    break
                logging.debug("Checking if all threads are alive")
                died_threadset = self._get_died_threadset()
                if len(died_threadset) > 0:
                    logging.critical("Some threads died: {}. Shutting down".format(", ".join(died_threadset)))
                    self.estop.set()
                    stop = True
                    break
                time_slept += type(self)._THREADSET_CHECK_INTERVAL
                if time_slept <= self.interval:
                    time.sleep(type(self)._THREADSET_CHECK_INTERVAL)
            if self.shutdown_init and not stop:  # The second check is needed if the shutdown was initiated during sleeping
                logging.debug("Shutdown initiated. Breaking the checker loop")
                stop = True
            if not stop:
                time_slept = 0
                logging.info("Requesting check")
                self.qchecker.put_nowait(Message().send_process_data(None))
            else:
                break

    def SvcStop(self):
        if self.mode != type(self)._MODE_SERVICE:
            raise Exception("Service can not stop if the instance mode is not \"{}\"".format(type(self)._MODE_SERVICE))
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.shutdown_init = True
        self.estop.set()

    def SvcDoRun(self):
        if self.mode != type(self)._MODE_SERVICE:
            raise Exception("Service can not run if the instance mode is not \"{}\"".format(type(self)._MODE_SERVICE))
        self._startup()
        self._run_checker()

    def DoStartup(self):
        if self.mode not in (type(self)._MODE_STANDALONE, type(self)._MODE_DISCOVERY):
            raise Exception("Startup can not be performed if the instance mode is not \"{}\" or \"{}\"".format(type(self)._MODE_STANDALONE, type(self)._MODE_DISCOVERY))
        self._startup()

    def DoShutdown(self):
        if self.mode not in (type(self)._MODE_STANDALONE, type(self)._MODE_DISCOVERY):
            raise Exception("Shutdown can not be performed if the instance mode is not \"{}\" or \"{}\"".format(type(self)._MODE_STANDALONE, type(self)._MODE_DISCOVERY))
        self.shutdown_init = True
        self.estop.set()

    def DoRunChecker(self):
        if self.mode != type(self)._MODE_STANDALONE:
            raise Exception("Checker can not run if the instance mode is not \"{}\"".format(type(self)._MODE_STANDALONE))
        self._run_checker()

    def DoDiscovery(self):
        if self.mode != type(self)._MODE_DISCOVERY:
            raise Exception("Discovery can not be performed if the instance mode is not \"{}\"".format(type(self)._MODE_DISCOVERY))
        logging.info("Performing discovery only")
        self.qdiscoverer.put_nowait(Message().send_process_data(None))
        self.ediscovery.wait()
        zabbix_data = {"data": [{
            "{#SITE_NAME}": site.get_name(),
            "{#SITE_START}": site.get_startuptype(),
            "{#SITE_PROTO}": site.get_pref_binding()["proto"],
            "{#SITE_HOST}": site.get_pref_binding()["host"],
            "{#SITE_ALL_HOSTS}": self._hostlist_separator.join(site.get_normalised_hostnames()),
            "{#SITE_PORT}": site.get_pref_binding()["port"],
            "{#SITE_ADDR}": site.get_pref_binding()["addr"]}
            for site in self.sites.get()]}
        return json.dumps(zabbix_data)


if __name__ == "__main__":

    cmd = argparse.ArgumentParser(description="IIS sites checker")
    group = cmd.add_mutually_exclusive_group()
    group.add_argument("-discover", help="perform sites discovery, print them in JSON format to STDOUT and exit",
                     action="store_true", default=False)
    group.add_argument("-register", help="write registry values required when the app is running in service mode",
                       action="store_true", default=False)
    cmd.add_argument("-configfile", help="path to config file")
    cmd.add_argument("-version", action="version", version=_FILE_VER)
    cmd.add_argument("mode", help="usage mode (*standalone)", choices=["standalone", "service"], nargs="?", default="standalone")
    cmd.add_argument("modeargs", help="arguments to be sent to the selected mode handler", nargs=argparse.REMAINDER)
    cmdargs = cmd.parse_args()

    if cmdargs.register:
        print("Registering {}".format(os.path.abspath(sys.argv[0])), file=sys.stderr)
        hk = win32api.RegCreateKeyEx(CheckerService._REG_KEY, CheckerService._REG_SUBKEY, win32con.KEY_WRITE)[0]
        win32api.RegSetValueEx(hk, CheckerService._REG_VALUE_NAME, 0, win32con.REG_SZ, os.path.abspath(sys.argv[0]))
    elif cmdargs.discover:
        checker = CheckerService(args=None, mode=CheckerService._MODE_DISCOVERY, configfile=cmdargs.configfile)
        checker.DoStartup()
        print(checker.DoDiscovery(), end="")
        logging.debug("Calling DoShutdown")
        checker.DoShutdown()
    elif cmdargs.mode == "standalone":
        checker = CheckerService(args=None, mode=CheckerService._MODE_STANDALONE, configfile=cmdargs.configfile)
        checker.DoStartup()
        try:
            checker.DoRunChecker()
        except KeyboardInterrupt:
            logging.info("User has requested to interrupt. Shutting down")
            checker.DoShutdown()
    elif cmdargs.mode == "service":
        svc_cmdargs = [sys.argv[0]] + cmdargs.modeargs
        win32serviceutil.HandleCommandLine(cls=CheckerService, argv=svc_cmdargs)
