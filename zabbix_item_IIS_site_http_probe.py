

import pycurl
import io
import urllib.parse as up
import re
import sys
import os.path
import configparser
from argparse import ArgumentParser
from ldap3.utils.ciDict import CaseInsensitiveDict as cidict
from cgi import parse_header
from sys import exit


# Constants
OK_MESSAGE = "ok"
CURL_FAILED_MESSAGE = "failed"
WEBSITE_FAILED_MESSAGE = "problem"
CFG_READ_ERROR_MESSAGE = "cfg_read_error"
CFG_PARSE_ERROR_MESSAGE = "cfg_parse_error"
CFG_OPTION_ERROR_MESSAGE = "cfg_option_error"
HTML_DEFAULT_CHARSET = "UTF-8"
HTML_FALLBACK_CHARSET = "ISO-8859-1"


cmd = ArgumentParser(description="Probes a Web site over http(s)")
cmd.add_argument("-scheme", help="Access scheme (protocol) (http or https)", default="http")
cmd.add_argument("-host", help="Host name", default="localhost")
cmd.add_argument("-allhosts",
                 metavar="NAME1,NAME2...",
                 help="Comma separated list of all host names of the host to be probed. "
                      "This list is used when searching in ini file for host-specific settings",
                 default=None)
cmd.add_argument("-port", help="Optional TCP port number", default=None)
cmd.add_argument("-addr", help="Optional IP address to connect to", default=None)
cmd.add_argument("-path", help="Path component of the URL", default="")
cmdgroup = cmd.add_mutually_exclusive_group()
cmdgroup.add_argument("-body", metavar="REGEXP", help="For successful operation, REGEXP must be found in the body", default=None)
cmdgroup.add_argument("-nobody", metavar="REGEXP", help="For successful operation, REGEXP must not be found in the body", default=None)
cmd.add_argument("-timeout", help="Operation timeout seconds (default is 5m)", default=300, type=int)
cmd.add_argument("-nameservers", metavar="NAME1,NAME2...", help="Comma separated list of name servers", default=None)
cmd.add_argument("-4", help="Resolve names to IPv4 only", dest="v4", action="store_true", default=False)
cmd.add_argument("-6", help="Resolve names to IPv6 only", dest="v6", action="store_true", default=False)
cmd.add_argument("-ca", help="Path to the CA certs bundle file (can be fetched from https://curl.haxx.se/ca/cacert.pem)",
                 default=None)
cmd.add_argument("-v", help="Verbose output (troubleshooting)", dest="verbose", action="store_true", default=False)
args = cmd.parse_args()
args.allhosts = set([x.strip().lower() for x in args.allhosts.split(",")]) if args.allhosts is not None else set()

cfg = configparser.ConfigParser()
try:
    cfg.read_file(open(os.path.join(
        os.path.dirname(sys.argv[0]),
        ".".join([os.path.basename(sys.argv[0]).split(".")[0], "ini"]))))
except FileNotFoundError:
    pass
except OSError:
    print(CFG_READ_ERROR_MESSAGE, end="")
    exit()
except configparser.Error:
    print(CFG_PARSE_ERROR_MESSAGE, end="")
    exit()
else:
    for section in cfg.sections():
        try:
            if args.allhosts & set([x.strip().lower() for x in re.split("\s*,\s*", cfg.get(section, "allhosts"))]):
                for option in cfg.options(section):
                    if option == "allhosts":
                        continue
                    elif option in {"body", "nobody"}:
                        if cfg.has_option(section, "body") ^ cfg.has_option(section, "nobody"):
                            args.body = None
                            args.nobody = None
                            setattr(args, option, cfg.get(section, option))
                        else:
                            print("{}, {}, {}".format(CFG_OPTION_ERROR_MESSAGE, section, option), end="")
                            exit()
                    elif option == "timeout":
                        args.timeout = cfg.getint(section, option)
                    elif option in {"v4", "v6", "verbose"}:
                        setattr(args, option, cfg.getboolean(section, option))
                    else:
                        setattr(args, option, cfg.get(section, option))
                break
        except configparser.NoOptionError:
            continue


class Website:

    well_known_ports = cidict({"http":"80", "https":"443"})

    def __init__(self, scheme="http", host="localhost", port="80", addr="127.0.0.1", path=""):
        if not re.search("^(http|https)$", scheme, re.I):
            raise RuntimeError("Unknown scheme {}".format(scheme))
        self.scheme = scheme
        self.host = "localhost" if host == "" else host
        self.addr = "127.0.0.1" if addr == "*" else addr
        self.port = port if port is not None else type(self).well_known_ports[scheme]
        self.path = path
        self.url = up.urlunparse(up.ParseResult(self.scheme, ":".join([self.host, self.port]), self.path, "", "", ""))
        self.curl_resolved_host = ":".join([self.host, self.port, self.addr]) if self.addr is not None else None

    def get_url(self):
        return self.url

    def get_curl_host(self):
        return self.curl_resolved_host


w = Website(args.scheme, args.host, args.port, args.addr, args.path)
buffer = io.BytesIO()
c = pycurl.Curl()
c.setopt(pycurl.URL, w.get_url())
if args.v4 ^ args.v6:
    if args.v4:
        c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V4)
    elif args.v6:
        c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_V6)
else:
    c.setopt(pycurl.IPRESOLVE, pycurl.IPRESOLVE_WHATEVER)
if args.nameservers:
    c.setopt(pycurl.DNS_SERVERS, args.nameservers)
if w.get_curl_host() is not None:
    c.setopt(pycurl.RESOLVE, [w.get_curl_host()])
if args.ca is not None:
    c.setopt(pycurl.CAINFO, args.ca)
c.setopt(pycurl.TIMEOUT, args.timeout)
c.setopt(pycurl.WRITEDATA, buffer)
c.setopt(pycurl.VERBOSE, args.verbose)
try:
    c.perform()
except pycurl.error:
    print(CURL_FAILED_MESSAGE, end="")
    exit()
else:
    response_info = {"code": c.getinfo(pycurl.RESPONSE_CODE),
                     "type": c.getinfo(pycurl.CONTENT_TYPE)}
    ct_params = cidict(parse_header(response_info["type"])[1]) if response_info["type"] is not None else cidict()
    response_info["charset"] = ct_params["charset"] if "charset" in ct_params else HTML_DEFAULT_CHARSET
finally:
    c.close()

if response_info["code"] >= 400:
    print(WEBSITE_FAILED_MESSAGE, end="")
    exit()

try:
    body = buffer.getvalue().decode(response_info["charset"])
except UnicodeDecodeError:
    try:
        body = buffer.getvalue().decode(HTML_FALLBACK_CHARSET)
    except ValueError:
        print(WEBSITE_FAILED_MESSAGE, end="")
        exit()

if args.body and not re.search(args.body, body, re.I):
    print(WEBSITE_FAILED_MESSAGE, end="")
    exit()
elif args.nobody and re.search(args.nobody, body, re.I):
    print(WEBSITE_FAILED_MESSAGE, end="")
    exit()

print(OK_MESSAGE, end="")
