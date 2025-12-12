from __future__ import annotations
import pytz

from inphms.orm import api

# put POSIX 'Etc/*' entries at the end to avoid confusing users - see bug 1086728
_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs


@api.model
def _lang_get(self):
    return self.env['res.lang'].get_installed()


EU_EXTRA_VAT_CODES = {
    'GR': 'EL',
    'GB': 'XI',
}

ADDRESS_FIELDS = ('street', 'street2', 'zip', 'city', 'state_id', 'country_id')
