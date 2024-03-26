import re
import socket
import psutil


def connect_urls(listen_url):
    """Get all the URLs that can be used to connect to the listen URL."""

    # split the url
    tcp_re = re.compile("^tcp://(?P<address>.+?):(?P<port>\d+)$")
    mo = tcp_re.match(listen_url)
    if mo is None:
        raise ValueError(f"unable to parse {listen_url}")

    address = mo['address']
    port = mo['port']

    urls = []
    if address == "0.0.0.0":
        local_addresses = local_ips()
        for address in local_addresses['ipv4']:
            urls.append(f'tcp://{address}:{port}')

    else:
        urls.append(url)

    return urls


def local_ips():
    """Returns all the local IP addresses on the host."""
    
    ipv4s = []
    ipv6s = []
    
    interfaces = psutil.net_if_addrs()
    for interface, if_addresses in interfaces.items():
        for if_address in if_addresses:
            if if_address.family == socket.AF_INET:
                ipv4s.append(if_address.address)
            elif if_address.family == socket.AF_INET6:
                ipv6s.append(if_address.address)
    
    addresses = {
        'ipv4': ipv4s,
        'ipv6': ipv6s
    }

    return addresses


