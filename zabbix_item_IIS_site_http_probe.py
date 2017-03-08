

import pycurl
import io
import urllib.parse as up
import re
from argparse import ArgumentParser


cmd = ArgumentParser(description="Probes a Web site over http(s)")
cmd.add_argument("-scheme", help="Access scheme (protocol) (http or https)", default="http")
cmd.add_argument("-host", help="Host name", default="localhost")
cmd.add_argument("-port", help="Optional TCP port number", default="80")
cmd.add_argument("-addr", help="Optional IP address to connect to", default=None)
cmd.add_argument("-path", help="Path component of the URL", default="")
cmd.add_argument("-timeout", help="Operation timeout (default is 5m)", default=300)
cmd.add_argument("-nameservers", help="Comma separated list of name servers", default=None)
cmd.add_argument("-4", help="Resolve names to IPv4 only", dest="v4", action="store_true", default=False)
cmd.add_argument("-6", help="Resolve names to IPv6 only", dest="v6", action="store_true", default=False)
cmd.add_argument("-v", help="Verbose output (troubleshooting)", dest="verbose", action="store_true", default=False)
args = cmd.parse_args()


class Website:

    def __init__(self, scheme="http", host="localhost", port="80", addr="127.0.0.1", path=""):
        if not re.search("^(http|https)$", scheme, re.I):
            raise RuntimeError("Unknown scheme {}".format(scheme))
        if host == "":
            host = "localhost"
        if addr == "*":
            addr = "127.0.0.1"
        self.scheme = scheme
        self.host = host
        self.port = port
        self.addr = addr
        self.path = path
        self.url = up.urlunparse(up.ParseResult(scheme, ":".join([host, port]), path, "", "", ""))
        self.curl_resolved_host = ":".join([host, port, addr]) if addr is not None else None

    def get_url(self):
        return self.url

    def get_curl_host(self):
        return self.curl_resolved_host


w = Website(args.scheme, args.host, args.port, args.addr, args.path)
buffer = io.BytesIO()
c = pycurl.Curl()
c.setopt(c.URL, w.get_url())
if args.v4 ^ args.v6:
    if args.v4:
        c.setopt(c.IPRESOLVE, c.IPRESOLVE_V4)
    elif args.v6:
        c.setopt(c.IPRESOLVE, c.IPRESOLVE_V6)
else:
    c.setopt(c.IPRESOLVE, c.IPRESOLVE_WHATEVER)
if args.nameservers:
    c.setopt(c.DNS_SERVERS, args.nameservers)
if w.get_curl_host() is not None:
    c.setopt(c.RESOLVE, [w.get_curl_host()])
c.setopt(c.FOLLOWLOCATION, True)
c.setopt(c.TIMEOUT, args.timeout)
c.setopt(c.WRITEDATA, buffer)
c.setopt(c.VERBOSE, args.verbose)
c.perform()
c.close()

body = buffer.getvalue()
print(body)
