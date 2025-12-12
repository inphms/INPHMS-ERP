from __future__ import annotations

from lxml import etree, objectify


# Configure default global parser
etree.set_default_parser(etree.XMLParser(resolve_entities=False))
default_parser = etree.XMLParser(resolve_entities=False, remove_blank_text=True)
default_parser.set_element_class_lookup(objectify.ObjectifyElementClassLookup())
objectify.set_default_parser(default_parser)