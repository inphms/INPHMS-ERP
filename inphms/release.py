
RELEASE_L = [ALPHA, BETA, CANDIDATE, FINAL] = ['alpha', 'beta', 'candidate', 'final']
RELEASE_LD = {ALPHA: 'a',
              BETA: 'b', 
              CANDIDATE: 'rc',
              FINAL: ''}

# VERSION_INFO = (MAJOR, MINOR, CORRECTION, RELEASE_LEVEL, REVISION, STATUS)
VERSION_INFO = (0, 1, 0, CANDIDATE, 0, 'e')
SERIES = SERIE = MAJOR = '.'.join(str(s) for s in VERSION_INFO[:2])
VERSION = SERIES + RELEASE_LD[VERSION_INFO[3]] + str(VERSION_INFO[4] or '') + '+' + VERSION_INFO[5]

PRODUCT_NAME = "INPHMS"
DESCRIPTION = "A simple ERP system."
LONG_DESC = '''INPHMS is a simple ERP system.
Stands for Intelligence Nusantara Plantation & Harvest Management System.
'''
CLASSIFIERS = """
DevelopmentStatus :: 1 - Planning
License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)
Operating System :: Microsoft :: Windows

Programming Language :: Python :: 3.12
"""
URL = "https://www.inphms.com"
AUTHOR = "INPHMS Team"
AUTHOR_EMAIL = "ian@inphms.com"
LICENSE = "LGPL-3"
NT_SERVICE_NAME = "INPHMS_SERVER_" + SERIES.replace('~','-')

MIN_PY_VERSION = (3, 10)
MAX_PY_VERSION = (3, 13)
MIN_PG_VERSION = 13
