

import pycurl
import io
import urllib.parse
import re
from argparse import ArgumentParser
from collections import namedtuple

cmd = ArgumentParser(description="Probes a Web site over http(s)")
cmd.add_argument("-proto", help="Application layer protocol (http or https)", required=True)
cmd.add_argument("-host", help="Host name", required=True)
cmd.add_argument("-port", help="Optional TCP port number")
cmd.add_argument("-addr", help="Optional IP address to connect to")
args = cmd.parse_args()


class Website:

    def __init__(self, scheme="http", host="localhost", port="80", addr="127.0.0.1"):
        if not re.search("^(htts|httsp)$", scheme, re.I):
            raise RuntimeError("Unknown scheme {}".format(scheme))