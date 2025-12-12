from __future__ import annotations
import hmac as hmac_lib
import hashlib
import zlib
import time
import datetime
import json
import base64

__all__ = ['consteq', 'hmac', 'limited_field_access_token', 'verify_limited_field_access_token',
           "hash_sign", "verify_hash_signed"]


consteq = hmac_lib.compare_digest


def hmac(env, scope, message, hash_function=hashlib.sha256):
    """Compute HMAC with `database.secret` config parameter as key.

    :param env: sudo environment to use for retrieving config parameter
    :param message: message to authenticate
    :param scope: scope of the authentication, to have different signature for the same
        message in different usage
    :param hash_function: hash function to use for HMAC (default: SHA-256)
    """
    if not scope:
        raise ValueError('Non-empty scope required')

    secret = env['ir.config_parameter'].get_param('database.secret')
    message = repr((scope, message))
    return hmac_lib.new(
        secret.encode(),
        message.encode(),
        hash_function,
    ).hexdigest()


def hash_sign(env, scope, message_values, expiration=None, expiration_hours=None):
    """ Generate an urlsafe payload signed with the HMAC signature for an iterable set of data.
    This feature is very similar to JWT, but in a more generic implementation that is inline with out previous hmac implementation.

    :param env: sudo environment to use for retrieving config parameter
    :param scope: scope of the authentication, to have different signature for the same
        message in different usage
    :param message_values: values to be encoded inside the payload
    :param expiration: optional, a datetime or timedelta
    :param expiration_hours: optional, a int representing a number of hours before expiration. Cannot be set at the same time as expiration
    :return: the payload that can be used as a token
    """
    assert not (expiration and expiration_hours)
    assert message_values is not None

    if expiration_hours:
        expiration = datetime.datetime.now() + datetime.timedelta(hours=expiration_hours)
    else:
        if isinstance(expiration, datetime.timedelta):
            expiration = datetime.datetime.now() + expiration
    expiration_timestamp = 0 if not expiration else int(expiration.timestamp())
    message_strings = json.dumps(message_values)
    hash_value = hmac(env, scope, f'1:{message_strings}:{expiration_timestamp}', hash_function=hashlib.sha256)
    token = b"\x01" + expiration_timestamp.to_bytes(8, 'little') + bytes.fromhex(hash_value) + message_strings.encode()
    return base64.urlsafe_b64encode(token).decode().rstrip('=')


def verify_hash_signed(env, scope, payload):
    """ Verify and extract data from a given urlsafe  payload generated with hash_sign()

    :param env: sudo environment to use for retrieving config parameter
    :param scope: scope of the authentication, to have different signature for the same
        message in different usage
    :param payload: the token to verify
    :return: The payload_values if the check was successful, None otherwise.
    """

    token = base64.urlsafe_b64decode(payload.encode()+b'===')
    version = token[:1]
    if version != b'\x01':
        raise ValueError('Unknown token version')

    expiration_value, hash_value, message = token[1:9], token[9:41].hex(), token[41:].decode()
    expiration_value = int.from_bytes(expiration_value, byteorder='little')
    hash_value_expected = hmac(env, scope, f'1:{message}:{expiration_value}', hash_function=hashlib.sha256)

    if consteq(hash_value, hash_value_expected) and (expiration_value == 0 or datetime.datetime.now().timestamp() < expiration_value):
        message_values = json.loads(message)
        return message_values
    return None


def limited_field_access_token(record, field_name, timestamp=None, *, scope):
    """ Generate a token granting access to the given record and field_name in
        the given scope.

        The validitiy of the token is determined by the timestamp parameter.
        When it is not specified, a timestamp is automatically generated with a
        validity of at least 14 days. For a given record and field_name, the
        generated timestamp is deterministic within a 14-day period (even across
        different days/months/years) to allow browser caching, and expires after
        maximum 42 days to prevent infinite access. Different record/field
        combinations expire at different times to prevent thundering herd problems.

        :param record: the record to generate the token for
        :type record: class:`inphms.models.Model`
        :param field_name: the field name of record to generate the token for
        :type field_name: str
        :param scope: scope of the authentication, to have different signature for the same
            record/field in different usage
        :type scope: str
        :param timestamp: expiration timestamp of the token, or None to generate one
        :type timestamp: int, optional
        :return: the token, which includes the timestamp in hex format
        :rtype: string
    """
    record.ensure_one()
    if not timestamp:
        unique_str = repr((record._name, record.id, field_name))
        two_weeks = 1209600  # 2 * 7 * 24 * 60 * 60
        start_of_period = int(time.time()) // two_weeks * two_weeks
        adler32_max = 4294967295
        jitter = two_weeks * zlib.adler32(unique_str.encode()) // adler32_max
        timestamp = hex(start_of_period + 2 * two_weeks + jitter)
    token = hmac(record.env(su=True), scope, (record._name, record.id, field_name, timestamp))
    return f"{token}o{timestamp}"


def verify_limited_field_access_token(record, field_name, access_token, *, scope):
    """Verify the given access_token grants access to field_name of record.
    In particular, the token must have the right format, must be valid for the
    given record, and must not have expired.

    :param record: the record to verify the token for
    :type record: class:`inphms.models.Model`
    :param field_name: the field name of record to verify the token for
    :type field_name: str
    :param access_token: the access token to verify
    :type access_token: str
    :param scope: scope of the authentication, to have different signature for the same
        record/field in different usage
    :return: whether the token is valid for the record/field_name combination at
        the current date and time
    :rtype: bool
    """
    *_, timestamp = access_token.rsplit("o", 1)
    return consteq(
        access_token, limited_field_access_token(record, field_name, timestamp, scope=scope)
    ) and datetime.datetime.now() < datetime.datetime.fromtimestamp(int(timestamp, 16))
