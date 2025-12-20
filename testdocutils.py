from inphms.addons.base.models.ir_module import utils
from docutils.core import publish_string

print(utils)
rst_content = """
Module Description
==================
This is a **test** description for the module.
"""

output = publish_string(rst_content, writer=utils.MyWriter())
print(output.decode('utf-8'))