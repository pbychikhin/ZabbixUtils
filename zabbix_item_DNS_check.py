

from dns import resolver, rdatatype, exception
from argparse import ArgumentParser
from socket import getfqdn


# Constants
OK_MESSAGE = "STATUS_OK"
DNS_TIMEOUT_MESSAGE = "STATUS_ERR_TIMEOUT"
DNS_NOTFOUND_MESSAGE = "STATUS_ERR_NOTFOUND"
DNS_ERROR_MESSAGE = "STATUS_ERR_DNS_PROBLEM"
DNS_TIMEOUT = 10


class verbose:
    def __init__(self, active=False):
        self.active = active
    def __call__(self, msg):
        if self.active:
            print(msg)


cmd = ArgumentParser(description="Probes a DNS server by requesting the SOA record")
cmd.add_argument("-name", help="Name to resolve. Default is the local host's domain", default=getfqdn().split(".", 1)[-1])
cmd.add_argument("-servers", help="Space separated list of name servers. Default is 127.0.0.1", default="127.0.0.1")
cmd.add_argument("-v", help="Verbose messaging", action="store_true", default=False)
args = cmd.parse_args()
args.servers = args.servers.split()
vmsg = verbose(args.v)


resolver.get_default_resolver().nameservers = args.servers
resolver.get_default_resolver().lifetime = DNS_TIMEOUT

vmsg("Resolving {}".format(args.name))
vmsg("Using name servers {}".format(resolver.get_default_resolver().nameservers))

try:
    resolver.query(args.name, rdatatype.SOA)
except exception.Timeout:
    print(DNS_TIMEOUT_MESSAGE, end="")
except resolver.NXDOMAIN:
    print(DNS_NOTFOUND_MESSAGE, end="")
except exception.DNSException:
    print(DNS_ERROR_MESSAGE, end="")
else:
    print(OK_MESSAGE, end="")
