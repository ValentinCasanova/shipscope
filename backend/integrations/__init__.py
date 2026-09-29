"""Clients for the outside APIs ShipScope calls (Layer 4).

Each client takes its configuration and HTTP session as arguments and raises its own
typed exceptions, so the code that uses it never deals with HTTP details. Nothing here
imports Django's ORM or Django REST framework.
"""
