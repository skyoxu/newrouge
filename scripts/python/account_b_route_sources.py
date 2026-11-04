#!/usr/bin/env python3
"""Prepare and account Task-free 3A source proposals; never formally adopts them."""
import sys
sys.dont_write_bytecode = True
from _b_route_sources import main

if __name__ == "__main__":
    raise SystemExit(main())
