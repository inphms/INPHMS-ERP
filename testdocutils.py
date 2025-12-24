from inphms.addons.base.models.ir_module import utils
from docutils.core import publish_string

def test_docutils():
    print(utils)
    rst_content = """
    Module Description
    ==================
    This is a **test** description for the module.
    """

    output = publish_string(rst_content, writer=utils.MyWriter())
    print(output.decode('utf-8'))

from lxml import etree
from inphms.tools import file_open
import os

def test_parse_doc():
    xml_file = './inphms/addons/base/views/base_menus.xml'
    with open(xml_file, 'r', encoding='utf-8') as file:
        xml_content = file.read()
        # print(xml_content)
        doc = etree.parse(xml_file)
        de = doc.getroot()
        for rec in de:
            print(rec.parent)
            print("*" * 10)
        # print(de.tag)

if __name__ == "__main__":
    test_parse_doc()