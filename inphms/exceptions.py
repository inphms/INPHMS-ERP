from __future__ import annotations
from http import HTTPStatus


class UserError(Exception):
    http_status = 422  # Unprocessable Entity
    def __init__(self, message):
        super().__init__(message)

class RedirectWarning(Exception):
    def __init__(self, message, action, button_text, additional_context=None):
        super().__init__(message, action, button_text, additional_context)

class AccessDenied(UserError):
    """ Login/password error.
    """
    http_status = 403  # Forbidden

    def __init__(self, message="Access Denied"):
        super().__init__(message)
        self.suppress_traceback()  # must be called in `except`s too

    def suppress_traceback(self):
        self.with_traceback(None)
        self.traceback = ('', '', '')
        # During handling of the above exception, another exception occurred
        self.__context__ = None
        # The above exception was the direct cause of the following exception
        self.__cause__ = None

class AccessError(UserError):
    """ Access rights error.
    """
    http_status = 403  # Forbidden


class CacheMiss(KeyError):
    """ Missing value(s) in cache.
    """

    def __init__(self, record, field):
        super().__init__("%r.%s" % (record, field.name))


class MissingError(UserError):
    """ Missing record(s).
    """
    http_status = 404  # Not Found


class LockError(UserError):
    """ Record(s) could not be locked.
    """
    http_status = 409  # Conflict


class ValidationError(UserError):
    """ Violation of python constraints.
    """


class ConcurrencyError(Exception):
    """ Signal that two concurrent transactions tried to commit something
        that violates some constraint.
    """

class RegistryError(RuntimeError):
    pass

class SessionExpiredException(Exception):
    http_status = HTTPStatus.FORBIDDEN


class MissingDependency(Exception):
    def __init__(self, msg_template: str, dependency: str):
        self.dependency = dependency
        super().__init__(msg_template.format(dependency=dependency))
