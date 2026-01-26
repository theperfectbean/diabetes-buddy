import socket
import urllib.request

# Force IPv4
original_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4_only

# Test
try:
    response = urllib.request.urlopen('https://pypi.org/simple/', timeout=5)
    print(f"Success! Status: {response.status}")
except Exception as e:
    print(f"Failed: {e}")
