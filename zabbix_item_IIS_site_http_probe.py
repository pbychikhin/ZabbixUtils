

import pycurl
import io
import urllib.parse as up
import re
from argparse import ArgumentParser


cmd = ArgumentParser(description="Probes a Web site over http(s)")
cmd.add_argument("-scheme", help="Access scheme (protocol) (http or https)", default="http")
cmd.add_argument("-host", help="Host name", default="localhost")
cmd.add_argument("-port", help="Optional TCP port number", default="80")
cmd.add_argument("-addr", help="Optional IP address to connect to", default="127.0.0.1")
cmd.add_argument("-path", help="Path component of the URL", default="")
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
        self.curl_resolved_host = ":".join([host, port, addr])

    def get_url(self):
        return self.url

    def get_curl_host(self):
        return self.curl_resolved_host

