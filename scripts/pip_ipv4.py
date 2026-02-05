import socket
import sys
import runpy

# Force IPv4
original_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4_only

# Run pip
sys.argv[0] = 'pip'
runpy.run_module('pip', run_name='__main__')
