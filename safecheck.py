import argparse
import binascii
import hashlib
import logging
import os
import pathlib
import sys

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

builtin_manifest_schema = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xfdu="urn:ccsds:schema:xfdu:1"
    targetNamespace="urn:ccsds:schema:xfdu:1" elementFormDefault="unqualified" attributeFormDefault="unqualified">
  <xs:simpleType name="locatorTypeType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="URL"/>
      <xs:enumeration value="OTHER"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:simpleType name="otherLocatorTypeType">
    <xs:restriction base="xs:string"/>
  </xs:simpleType>
  <xs:attributeGroup name="LOCATION">
    <xs:attribute name="locatorType" use="required" type="xfdu:locatorTypeType"/>
    <xs:attribute name="otherLocatorType" type="xfdu:otherLocatorTypeType"/>
  </xs:attributeGroup>
  <xs:attributeGroup name="registrationGroup">
    <xs:attribute name="registrationAuthority" type="xs:string" use="optional"/>
    <xs:attribute name="registeredID" type="xs:string" use="optional"/>
  </xs:attributeGroup>
  <xs:simpleType name="vocabularyNameType">
    <xs:restriction base="xs:string"/>
  </xs:simpleType>
  <xs:simpleType name="versionType">
    <xs:restriction base="xs:string"/>
  </xs:simpleType>
  <xs:simpleType name="mimeTypeType">
    <xs:restriction base="xs:string"/>
  </xs:simpleType>
  <xs:simpleType name="checksumNameType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="MD5"/>
      <xs:enumeration value="CRC32"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:simpleType name="combinationMethodType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="concat"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:attribute name="namespace" type="xs:string"/>
  <xs:complexType name="referenceType">
    <xs:sequence/>
    <xs:attribute name="href" type="xs:string" use="required"/>
    <xs:attribute name="ID" type="xs:ID"/>
    <xs:attribute name="textInfo" type="xs:string"/>
    <xs:attributeGroup ref="xfdu:LOCATION"/>
    <xs:attribute name="locator" type="xs:string" use="optional" default="/"/>
  </xs:complexType>
  <xs:complexType name="checksumInformationType">
    <xs:simpleContent>
      <xs:extension base="xs:string">
        <xs:attribute name="checksumName" type="xfdu:checksumNameType" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>
  <xs:complexType name="metadataObjectType">
    <xs:sequence>
      <xs:element name="metadataReference" type="xfdu:metadataReferenceType" minOccurs="0"/>
      <xs:element name="metadataWrap" type="xfdu:metadataWrapType" minOccurs="0"/>
      <xs:element name="dataObjectPointer" type="xfdu:dataObjectPointerType" minOccurs="0"/>
    </xs:sequence>
    <xs:attribute name="ID" use="required">
      <xs:simpleType>
        <xs:restriction base="xs:ID">
          <xs:pattern value="processing"/>
          <xs:pattern value="(a|.+A)cquisitionPeriod"/>
          <xs:pattern value="(p|.+P)latform"/>
          <xs:pattern value=".+Schema"/>
          <xs:pattern value=".+QualityInformation"/>
          <xs:pattern value=".+OrbitReference"/>
          <xs:pattern value=".+GridReference"/>
          <xs:pattern value=".+FrameSet"/>
          <xs:pattern value=".+Index"/>
          <xs:pattern value=".+Annotation"/>
          <xs:pattern value=".+Information"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
    <xs:attribute name="classification">
      <xs:simpleType>
        <xs:restriction base="xs:string">
          <xs:enumeration value="DED"/>
          <xs:enumeration value="SYNTAX"/>
          <xs:enumeration value="FIXITY"/>
          <xs:enumeration value="PROVENANCE"/>
          <xs:enumeration value="CONTEXT"/>
          <xs:enumeration value="REFERENCE"/>
          <xs:enumeration value="DESCRIPTION"/>
          <xs:enumeration value="OTHER"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
    <xs:attribute name="category">
      <xs:simpleType>
        <xs:restriction base="xs:string">
          <xs:enumeration value="REP"/>
          <xs:enumeration value="PDI"/>
          <xs:enumeration value="DMD"/>
          <xs:enumeration value="OTHER"/>
          <xs:enumeration value="ANY"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
  </xs:complexType>
  <xs:complexType name="metadataReferenceType">
    <xs:sequence/>
    <xs:attribute name="href" type="xs:string" use="required"/>
    <xs:attribute name="ID" type="xs:ID"/>
    <xs:attribute name="textInfo" type="xs:string"/>
    <xs:attributeGroup ref="xfdu:LOCATION"/>
    <xs:attribute name="locator" type="xs:string" use="optional" default="/"/>
    <xs:attribute name="vocabularyName" type="xfdu:vocabularyNameType"/>
    <xs:attribute name="mimeType" type="xfdu:mimeTypeType"/>
  </xs:complexType>
  <xs:complexType name="xmlDataType">
    <xs:sequence>
      <xs:any namespace="##any" processContents="lax" maxOccurs="unbounded"/>
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="fileContentType">
    <xs:choice>
      <xs:element name="binaryData" type="xs:base64Binary" minOccurs="0"/>
      <xs:element name="xmlData" type="xfdu:xmlDataType" minOccurs="0"/>
    </xs:choice>
    <xs:attribute name="ID" type="xs:ID"/>
  </xs:complexType>
  <xs:complexType name="metadataWrapType">
    <xs:sequence>
      <xs:element name="xmlData" type="xfdu:xmlDataType"/>
    </xs:sequence>
    <xs:attribute name="mimeType" type="xfdu:mimeTypeType"/>
    <xs:attribute name="textInfo" type="xs:string"/>
    <xs:attribute name="vocabularyName" type="xfdu:vocabularyNameType"/>
  </xs:complexType>
  <xs:complexType name="dataObjectPointerType">
    <xs:attribute name="ID" type="xs:ID"/>
    <xs:attribute name="dataObjectID" use="required" type="xs:IDREF"/>
  </xs:complexType>
  <xs:complexType name="keyDerivationType">
    <xs:attribute name="name" use="required" type="xs:string"/>
    <xs:attribute name="salt" use="required">
      <xs:simpleType>
        <xs:restriction base="xs:string">
          <xs:length value="16"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
    <xs:attribute name="iterationCount" use="required" type="xs:long"/>
  </xs:complexType>
  <xs:element name="abstractKeyDerivation" type="xfdu:keyDerivationType" abstract="true"/>
  <xs:element name="keyDerivation" type="xfdu:keyDerivationType" substitutionGroup="xfdu:abstractKeyDerivation"/>
  <xs:complexType name="transformObjectType">
    <xs:sequence>
      <xs:element name="algorithm" type="xs:string"/>
      <xs:element ref="xfdu:abstractKeyDerivation" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="ID" type="xs:ID"/>
    <xs:attribute name="order" type="xs:string"/>
    <xs:attribute name="transformType" use="required">
      <xs:simpleType>
        <xs:restriction base="xs:string">
          <xs:enumeration value="COMPRESSION"/>
          <xs:enumeration value="AUTHENTICATION"/>
          <xs:enumeration value="ENCRYPTION"/>
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
  </xs:complexType>
  <xs:complexType name="byteStreamType">
    <xs:sequence>
      <xs:element name="fileLocation" type="xfdu:referenceType"/>
      <xs:element name="checksum" type="xfdu:checksumInformationType"/>
      <!-- start: L0 specific -->
      <xs:element name="byteOrder" minOccurs="0">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:enumeration value="LITTLE_ENDIAN"/>
            <xs:enumeration value="BIG_ENDIAN"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="averageBitRate" type="xs:long" minOccurs="0"/>
      <!-- end: L0 specific -->
    </xs:sequence>
    <xs:attribute name="ID" use="optional" type="xs:ID"/>
    <xs:attribute name="mimeType" type="xfdu:mimeTypeType" use="required"/>
    <xs:attribute name="size" type="xs:long"/>
  </xs:complexType>
  <xs:complexType name="dataObjectType">
    <xs:sequence>
      <xs:element name="byteStream" type="xfdu:byteStreamType" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="ID" type="xs:ID" use="required"/>
    <xs:attribute name="repID" type="xs:IDREFS" use="required"/>
    <xs:attribute name="size" type="xs:long"/>
    <xs:attribute name="combinationName" type="xfdu:combinationMethodType" use="optional"/>
    <xs:attributeGroup ref="xfdu:registrationGroup"/>
  </xs:complexType>
  <xs:complexType name="dataObjectSectionType">
    <xs:sequence>
      <xs:element name="dataObject" type="xfdu:dataObjectType" maxOccurs="unbounded"/>
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="contentUnitType">
    <xs:sequence>
      <xs:element name="dataObjectPointer" type="xfdu:dataObjectPointerType" minOccurs="0"/>
      <xs:element ref="xfdu:abstractContentUnit" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="ID" type="xs:ID" use="optional"/>
    <xs:attribute name="order" type="xs:string"/>
    <xs:attribute name="unitType" type="xs:string"/>
    <xs:attribute name="textInfo" type="xs:string"/>
    <xs:attribute name="repID" type="xs:IDREFS"/>
    <xs:attribute name="dmdID" type="xs:IDREFS"/>
    <xs:attribute name="pdiID" type="xs:IDREFS"/>
    <xs:attribute name="anyMdID" type="xs:IDREFS"/>
    <xs:attribute name="behaviorID" type="xs:IDREF"/>
    <xs:anyAttribute namespace="##other" processContents="lax"/>
  </xs:complexType>
  <xs:element name="abstractContentUnit" type="xfdu:contentUnitType" abstract="true"/>
  <xs:element name="contentUnit" type="xfdu:contentUnitType" substitutionGroup="xfdu:abstractContentUnit"/>
  <xs:complexType name="informationPackageMapType">
    <xs:sequence>
      <xs:element ref="xfdu:abstractContentUnit"/>
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="interfaceDefinitionType">
    <xs:complexContent>
      <xs:extension base="xfdu:referenceType">
        <xs:sequence>
          <xs:element name="inputParameter" minOccurs="0" maxOccurs="unbounded">
            <xs:complexType mixed="true">
              <xs:sequence>
                <xs:element name="dataObjectPointer" type="xfdu:dataObjectPointerType" minOccurs="0"/>
              </xs:sequence>
              <xs:attribute name="name" use="required" type="xs:string"/>
              <xs:attribute name="value" type="xs:string"/>
            </xs:complexType>
          </xs:element>
        </xs:sequence>
      </xs:extension>
    </xs:complexContent>
  </xs:complexType>
  <xs:element name="abstractMechanism" type="xfdu:mechanismType" abstract="true"/>
  <xs:complexType name="mechanismType">
    <xs:complexContent>
      <xs:extension base="xfdu:referenceType"/>
    </xs:complexContent>
  </xs:complexType>
  <xs:complexType name="metadataSectionType">
    <xs:sequence>
      <xs:element name="metadataObject" type="xfdu:metadataObjectType" minOccurs="2" maxOccurs="unbounded"/>
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="XFDUType">
    <xs:sequence>
      <xs:element name="informationPackageMap" type="xfdu:informationPackageMapType"/>
      <xs:element name="metadataSection" type="xfdu:metadataSectionType" minOccurs="0"/>
      <xs:element name="dataObjectSection" type="xfdu:dataObjectSectionType" minOccurs="0"/>
    </xs:sequence>
    <xs:attribute name="version" type="xfdu:versionType" use="required"/>
  </xs:complexType>
  <xs:element name="XFDU" type="xfdu:XFDUType"/>
</xs:schema>
"""


def check_file_against_schema(xmlfile, schema):
    if isinstance(schema, str) and schema.startswith('<?xml'):
        xmlschema = etree.XMLSchema(etree.fromstring(schema))
        schema = "built-in schema"
    else:
        xmlschema = etree.XMLSchema(etree.parse(os.fspath(schema)).getroot())
    try:
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


def check_product_crc(product, manifestfile):
    expected_crc = format(binascii.crc_hqx(pathlib.Path(manifestfile).read_bytes(), 0xFFFF), '04X')
    actual_crc = pathlib.Path(product).stem[-4:]
    if expected_crc != actual_crc:
        logger.warning(f"crc in product name '{actual_crc}' does not match crc of manifest file '{expected_crc}'")
        return False
    return True


def check_manifest_file(file, schema=None):
    if schema is None:
        schema = builtin_manifest_schema
    return check_file_against_schema(file, schema)


def verify_safe_product(product, manifest_schema=None):
    has_errors = False
    has_warnings = False

    product = pathlib.Path(product)

    if not product.exists():
        logger.error(f"could not find '{product}'")
        return 2

    manifestfile = product / 'manifest.safe'
    if not manifestfile.exists():
        logger.error(f"could not find '{manifestfile}'")
        return 2

    if product.name[4:7] != "AUX":
        if not check_product_crc(product, manifestfile):
            has_warnings = True

    if not check_manifest_file(manifestfile, manifest_schema):
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
