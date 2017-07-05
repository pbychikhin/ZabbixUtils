

from dns import resolver, rdatatype, exception
from argparse import ArgumentParser
from socket import getfqdn


# Constants
OK_MESSAGE = "STATUS_OK"
DNS_TIMEOUT_MESSAGE = "STATUS_ERR_TIMEOUT"
DNS_NOTFOUND_MESSAGE = "STATUS_ERR_NOTFOUND"
DNS_ERROR_MESSAGE = "STATUS_ERR_DNS_PROBLEM"


cmd = ArgumentParser(description="Probes a DNS server")
cmd.add_argument("-name", help="Name to resolve. Default is local host's FQDN", default=getfqdn())
cmd.add_argument("-servers", help="Space separated list of name servers. Default is 127.0.0.1", default="127.0.0.1")
args = cmd.parse_args()
args.servers = args.servers.split()


resolver.get_default_resolver().nameservers = args.servers
resolver.get_default_resolver().lifetime = 10

try:
    resolver.query("sysonline.com", rdatatype.SOA)
except exception.Timeout:
    print(DNS_TIMEOUT_MESSAGE, end="")
except resolver.NXDOMAIN:
    print(DNS_NOTFOUND_MESSAGE, end="")
except exception.DNSException:
    print(DNS_ERROR_MESSAGE, end="")