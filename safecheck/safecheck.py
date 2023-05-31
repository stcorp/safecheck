import argparse
import binascii
import hashlib
import logging
import os
import pathlib
import sys
from importlib import resources

from lxml import etree


logger = logging.getLogger(__name__)


__copyright__ = 'Copyright (C) 2011-2023 S[&]T, The Netherlands.'
__version__ = '3.0'

"""Perform consistency checks on SAFE products.

Check the contents of the SAFE products against information included in
the manifest file, and also perform checks on the components size and
checksums.

All XML files included in the product are checked against their schema
(if available).

Additional checks on consistency between the product name and information
included in the manifest file are also performed.
"""

NSXFDU = '{urn:ccsds:schema:xfdu:1}'


def check_file_against_schema(xmlfile, schema):
    if isinstance(schema, str) and schema.startswith('<?xml'):
        xmlschema = etree.XMLSchema(etree.fromstring(schema))
        schema = "built-in schema"
    else:
        try:
            etree.clear_error_log()
            xmlschema = etree.XMLSchema(etree.parse(os.fspath(schema)).getroot())
        except etree.Error as exc:
            logger.error(f"could not parse schema '{schema}'")
            for error in exc.error_log:
                logger.error(f"{error.filename}:{error.line}: {error.message}")
            return False
    try:
        etree.clear_error_log()
        xmlschema.assertValid(etree.parse(os.fspath(xmlfile)))
    except etree.DocumentInvalid as exc:
        logger.error(f"could not verify '{xmlfile}' against schema '{schema}'")
        for error in exc.error_log:
            logger.error(f"{error.filename}:{error.line}: {error.message}")
        return False
    logger.debug(f"file '{xmlfile}' valid according to schema '{schema}'")
    return True


def is_xml(filename):
    filename = pathlib.Path(filename)
    return filename.suffix.lower() == '.xml' and filename.name[0] != "."


def md5sum(filename):
    md5 = hashlib.md5()
    with open(filename, 'rb') as fd:
        while True:
            data = fd.read(65536)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


def s1_check_product_crc(product, manifestfile):
    """
    Check CRC part of the product name.
    Only applies to S1 products
    """
    expected_crc = format(binascii.crc_hqx(pathlib.Path(manifestfile).read_bytes(), 0xFFFF), '04X')
    # Standard products the CRC is the last 4 chararcters in the productname, before the .SAFE extension
    # This is as well the 9th subpart of product name while splitting using '_'
    # On GRD/COG products, an additional '_COG' is added in product name
    actual_crc = pathlib.Path(product).stem.split('_')[8]
    if expected_crc != actual_crc:
        logger.warning(f"crc in product name '{actual_crc}' does not match crc of manifest file '{expected_crc}'")
        return False
    return True


def get_default_manifest_schema(mission: str) -> str:
    path = f"xsd/{mission.lower()}_buildin_manifest.xsd"
    resource = resources.files(__package__).joinpath(path)
    if resource.exists():
        return resource.read_text()
    else:
        raise FileNotFoundError(f"resource not found: {path!r}")


def check_manifest_file(file, schema=None, mission=None):
    if schema is None:
        schema = get_default_manifest_schema(mission)
    return check_file_against_schema(file, schema)


def verify_safe_product(product, manifest_schema=None):
    has_errors = False
    has_warnings = False

    product = pathlib.Path(product)

    mission = product.name[0:2]

    if not product.exists():
        logger.error(f"could not find '{product}'")
        return 2

    manifestfile = product / 'manifest.safe'
    if not manifestfile.exists():
        logger.error(f"could not find '{manifestfile}'")
        return 2

    if mission == "S1" and product.name[4:7] != "AUX":
        if not s1_check_product_crc(product, manifestfile):
            has_warnings = True

    if not check_manifest_file(manifestfile, manifest_schema, mission=mission):
        has_errors = True
    manifest = etree.parse(os.fspath(manifestfile))
    if manifest is None:
        logger.error(f"could not parse xml file '{manifestfile}'")
        return 2

    # find list of files in product
    files = [item for item in product.rglob("*") if item.is_file()]
    files.remove(manifestfile)

    # check files that are referenced in manifest file
    data_objects = {}
    reps = {}

    metadata_section = manifest.find('metadataSection')
    for metadata_object in metadata_section.findall('metadataObject'):
        ID = metadata_object.get('ID')
        if ID.endswith("Schema"):
            rep_id = ID
            href = metadata_object.find('metadataReference').get('href')
            reps[rep_id] = {'ID': rep_id, 'href': href}
            filepath = product / href
            if filepath in files:
                files.remove(filepath)

    if mission == 'S1':
        information_package_map = manifest.find('informationPackageMap')
        for content_unit in information_package_map.findall(f'{NSXFDU}contentUnit/{NSXFDU}contentUnit'):
            data_object_id = content_unit.find('dataObjectPointer').get('dataObjectID')
            rep_id = content_unit.get('repID')
            # rep_id can be a space separated list of IDs (first one contains the main schema)
            rep_id = rep_id.split()[0]
            if rep_id not in reps:
                logger.error(f"dataObject '{data_object_id}' in informationPackageMap contains repID '{rep_id}' which "
                             f"is not defined in metadataSection")
                return 2
            data_objects[data_object_id] = {'rep': reps[rep_id]}

    data_object_section = manifest.find('dataObjectSection')
    for data_object in data_object_section.findall('dataObject'):
        data_object_id = data_object.get('ID')
        if data_object_id not in data_objects:
            logger.error(f"dataObject '{data_object_id}' in dataObjectSection is not defined in informationPackageMap")
            return 2
        rep_id = data_object.get('repID')
        # rep_id can be a space separated list of IDs (first one contains the main schema)
        rep_id = rep_id.split()[0]
        if data_objects[data_object_id]['rep']['ID'] != rep_id:
            logger.error(f"dataObject '{data_object_id}' contains repID '{data_objects[data_object_id]['rep']['ID']}' "
                         f"in informationPackageMap, but '{rep_id}' in dataObjectSection")
            has_errors = True
        size = data_object.find('byteStream').get('size')
        href = data_object.find('byteStream/fileLocation').get('href')
        checksum = data_object.find('byteStream/checksum').text
        data_objects[data_object_id]['size'] = size
        data_objects[data_object_id]['href'] = href
        data_objects[data_object_id]['checksum'] = checksum
        filepath = product / href
        if filepath in files:
            files.remove(filepath)

    keys = list(data_objects.keys())
    keys.sort(key=lambda x: data_objects[x]['href'])
    for key in keys:
        data_object = data_objects[key]
        filepath = product / data_object['href']
        # check existence of file
        if not filepath.exists():
            logger.error(f"manifest.safe reference '{filepath}' does not exist")
            has_errors = True
            continue
        # check file size
        filesize = filepath.stat().st_size
        if filesize != int(data_object['size']):
            logger.error(f"file size for '{filepath}' ({filesize}) does not match file size in manifest.safe "
                         f"({data_object['size']})")
            has_errors = True
        # check md5sum
        checksum = md5sum(filepath)
        if checksum != data_object['checksum']:
            logging.error(f"checksum for '{filepath}' ({checksum}) does not match checksum in manifest.safe "
                          f"({data_object['checksum']})")
            has_errors = True
        # check with XML Schema (if the file is an xml file)
        if is_xml(filepath) and data_object['rep']:
            schema = product / data_object['rep']['href']
            if not schema.exists():
                logging.error(f"schema file '{schema}' does not exist")
                has_errors = True
            elif not check_file_against_schema(filepath, schema):
                has_errors = True

    # Report on files in the SAFE package that are not referenced by the manifset.safe file
    for file in files:
        logging.warning(f"file '{file}' found in product but not included in manifest.safe")
        has_warnings = True

    if has_errors:
        return 2
    if has_warnings:
        return 3
    return 0


def main():
    logging.basicConfig(format='%(levelname)s: %(message)s', stream=sys.stdout)
    logging.captureWarnings(True)

    # This parser is used in combination with the parse_known_args() function as a way to implement a "--version"
    # option that prints version information and exits, and is included in the help message.
    #
    # The "--version" option should have the same semantics as the "--help" option in that if it is present on the
    # command line, the corresponding action should be invoked directly, without checking any other arguments.
    # However, the argparse module does not support user defined options with such semantics.
    version_parser = argparse.ArgumentParser(add_help=False)
    version_parser.add_argument('--version', action='store_true', help='output version information and exit')

    parser = argparse.ArgumentParser(prog='safecheck', description=__doc__, parents=[version_parser])
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='suppress standard output messages and warnings, only errors are printed to screen')
    parser.add_argument('-s', '--schema', help='path to the XML schema file for the product manifest')
    parser.add_argument('products', nargs='+', metavar='<SAFE product>')

    args, unused_args = version_parser.parse_known_args()
    if args.version:
        print(f'safecheck v{__version__}')
        print(__copyright__)
        print()
        sys.exit(0)

    args = parser.parse_args(unused_args)

    logging.getLogger().setLevel('ERROR' if args.quiet else 'INFO')
    try:
        return_code = 0
        for arg in args.products:
            if not args.quiet:
                print(arg)
            result = verify_safe_product(arg, args.schema)
            if result != 0:
                if result < return_code or return_code == 0:
                    return_code = result
            if not args.quiet:
                print('')
        sys.exit(return_code)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        sys.exit(1)


if __name__ == '__main__':
    main()
