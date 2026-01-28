"""
Network configuration for Diabetes Buddy agents.

Forces IPv4 connections to avoid IPv6 timeout issues with Google APIs.
Import this module before any google.genai imports.
"""

import socket

_original_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_ipv4_only(*args, **kwargs):
    """Filter getaddrinfo results to only return IPv4 addresses."""
    responses = _original_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]


def force_ipv4():
    """Force all socket connections to use IPv4."""
    socket.getaddrinfo = _getaddrinfo_ipv4_only


# Auto-apply on import
force_ipv4()
