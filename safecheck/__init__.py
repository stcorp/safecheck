"""Perform consistency checks on SAFE products."""

from .safecheck import (
    __version__,
    check_file_against_schema,
    s1_check_product_crc,
    get_default_manifest_schema,
    check_manifest_file,
    verify_safe_product,
)
