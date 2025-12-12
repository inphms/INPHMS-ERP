from __future__ import annotations
import email
import email.policy
import idna
import logging
import re
import smtplib

from urllib3.contrib.pyopenssl import get_subj_alt_name

try:
    # urllib3 1.26 (ubuntu jammy and up, debian bullseye and up)
    from urllib3.util.ssl_match_hostname import CertificateError, match_hostname
except ImportError:
    # urllib3 1.25 and below
    from urllib3.packages.ssl_match_hostname import CertificateError, match_hostname

from inphms.tools import formataddr

_logger = logging.getLogger(__name__)
_test_logger = logging.getLogger('inphms.tests')

SMTP_TIMEOUT = 60


class MailDeliveryException(Exception):
    """Specific exception subclass for mail delivery errors"""


# Python 3: patch SMTP's internal printer/debugger
def _print_debug(self, *args):
    _logger.debug(' '.join(str(a) for a in args))
smtplib.SMTP._print_debug = _print_debug

# Python 3: workaround for bpo-35805, only partially fixed in Python 3.8.
RFC5322_IDENTIFICATION_HEADERS = {'message-id', 'in-reply-to', 'references', 'resent-msg-id'}
_noFoldPolicy = email.policy.SMTP.clone(max_line_length=None)
class IdentificationFieldsNoFoldPolicy(email.policy.EmailPolicy):
    # Override _fold() to avoid folding identification fields, excluded by RFC2047 section 5
    # These are particularly important to preserve, as MTAs will often rewrite non-conformant
    # Message-ID headers, causing a loss of thread information (replies are lost)
    def _fold(self, name, value, *args, **kwargs):
        if name.lower() in RFC5322_IDENTIFICATION_HEADERS:
            return _noFoldPolicy._fold(name, value, *args, **kwargs)
        return super()._fold(name, value, *args, **kwargs)

# Global monkey-patch for our preferred SMTP policy, preserving the non-default linesep
email.policy.SMTP = IdentificationFieldsNoFoldPolicy(linesep=email.policy.SMTP.linesep)

# Python 2: replace smtplib's stderr
class WriteToLogger(object):
    def write(self, s):
        _logger.debug(s)
smtplib.stderr = WriteToLogger()

def is_ascii(s):
    return all(ord(cp) < 128 for cp in s)

address_pattern = re.compile(r'([^" ,<@]+@[^>" ,]+)')

def extract_rfc2822_addresses(text):
    """Returns a list of valid RFC2822 addresses
       that can be found in ``source``, ignoring
       malformed ones and non-ASCII ones.
    """
    if not text:
        return []
    candidates = address_pattern.findall(text)
    valid_addresses = []
    for c in candidates:
        try:
            valid_addresses.append(formataddr(('', c), charset='ascii'))
        except idna.IDNAError:
            pass
    return valid_addresses


def _verify_check_hostname_callback(cnx, x509, err_no, err_depth, return_code, *, hostname):
    """Callback used for pyOpenSSL.verify_mode, by default pyOpenSSL
       only checkes :param:`err_no`, we enrich it to also verify that
       the SMTP server :param:`hostname` matches the :param:`x509`'s
       Common Name (CN) or Subject Alternative Name (SAN)."""
    if err_no:
        return False

    if err_depth == 0:  # leaf certificate
        peercert = {
            "subject": ((("commonName", x509.get_subject().CN),),),
            "subjectAltName": get_subj_alt_name(x509),
        }
        match_hostname(peercert, hostname)  # it raises when it does not match

    return True
