#!/usr/bin/env python3

"""Generates a standalone unix executable for safecheck.

From the paxkage root folder run the following command::

  $ python3 mkzipapp.py

It generates a standalone executable in `dist/safecheck` that can be used
to perform consistency checks on SAFE products.
"""

import pathlib
import zipapp

def safecheck_filter(x):
    return x.match("safecheck/*.py") or x.match("safecheck/xsd/*.xsd")


pathlib.Path("dist").mkdir(exist_ok=True)


zipapp.create_archive(
    source=".",
    target="dist/safecheck",
    interpreter="/usr/bin/env python3",
    main="safecheck:main",
    filter=safecheck_filter,
)
