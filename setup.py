#!/usr/bin/env python
# ruff: noqa: F821

from setuptools import find_namespace_packages, setup
from os.path import join, dirname

exec(open(join(dirname(__file__), 'inphms', 'release.py'), 'rb').read())
library_name = 'inphms'

setup(
    name="inphms",
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESC,
    url=URL,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    classifiers=[c for c in CLASSIFIERS.split('\n') if c],
    license=LICENSE,
    scripts=['setup/inphms'],
    packages=find_namespace_packages(),
    package_dir={'%s' % library_name: 'inphms'},
    include_package_data=True,
    install_requires=[
        'asn1crypto',
        'babel >= 1.0',
        'cbor2',
        'chardet',
        'cryptography',
        'docutils',
        'geoip2',
        'gevent',
        'greenlet',
        'idna',
        'Jinja2',
        'lxml',  # windows binary http://www.lfd.uci.edu/~gohlke/pythonlibs/
        'lxml_html_clean',
        'libsass',
        'MarkupSafe',
        'num2words',
        'ofxparse',
        'openpyxl',
        'passlib',
        'pillow',  # windows binary http://www.lfd.uci.edu/~gohlke/pythonlibs/
        'polib',
        'psutil',  # windows binary code.google.com/p/psutil/downloads/list
        'psycopg2 >= 2.2',
        'pyopenssl',
        'PyPDF2',
        'pyserial',
        'python-dateutil',
        'python-stdnum',
        'pytz',
        'pyusb >= 1.0.0b1',
        'qrcode',
        'reportlab',  # windows binary pypi.python.org/pypi/reportlab
        'rjsmin',
        'requests',
        'urllib3',
        'vobject',
        'werkzeug',
        'xlrd',
        'xlsxwriter',
        'xlwt',
        'zeep',
    ],
    python_requires='>=' + ".".join(map(str, MIN_PY_VERSION)),
    extras_require={
        'ldap': ['python-ldap'],
    },
    tests_require=[
        'freezegun',
    ],
)