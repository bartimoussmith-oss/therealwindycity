#!/usr/bin/env python3
"""Promethean local CLI; importing performs no network or writes."""
from promethean.sdk import main
if __name__=='__main__':
    raise SystemExit(main())
