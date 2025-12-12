import logging

from inphms.exceptions import UserError


#########
# CONST #
#########
WEBHOOK_SAMPLE_VALUES = {
    "integer": 42,
    "float": 42.42,
    "monetary": 42.42,
    "char": "Hello World",
    "text": "Hello World",
    "html": "<p>Hello World</p>",
    "boolean": True,
    "selection": "option1",
    "date": "2020-01-01",
    "datetime": "2020-01-01 00:00:00",
    "binary": "<base64_data>",
    "many2one": 47,
    "many2many": [42, 47],
    "one2many": [42, 47],
    "reference": "res.partner,42",
    None: "some_data",
}


VIEW_TYPES = [
    ('list', 'List'),
    ('form', 'Form'),
    ('graph', 'Graph'),
    ('pivot', 'Pivot'),
    ('calendar', 'Calendar'),
    ('kanban', 'Kanban'),
]


##########
# LOGGER #
##########
_logger = logging.getLogger(__name__)
_server_action_logger = _logger.getChild("server_action_safe_eval")

class LoggerProxy:
    """ Proxy of the `_logger` element in order to be used in server actions.
    We purposefully restrict its method as it will be executed in `safe_eval`.
    """
    @staticmethod
    def log(level, message, *args, stack_info=False, exc_info=False):
        _server_action_logger.log(level, message, *args, stack_info=stack_info, exc_info=exc_info)

    @staticmethod
    def info(message, *args, stack_info=False, exc_info=False):
        _server_action_logger.info(message, *args, stack_info=stack_info, exc_info=exc_info)

    @staticmethod
    def warning(message, *args, stack_info=False, exc_info=False):
        _server_action_logger.warning(message, *args, stack_info=stack_info, exc_info=exc_info)

    @staticmethod
    def error(message, *args, stack_info=False, exc_info=False):
        _server_action_logger.error(message, *args, stack_info=stack_info, exc_info=exc_info)

    @staticmethod
    def exception(message, *args, stack_info=False, exc_info=True):
        _server_action_logger.exception(message, *args, stack_info=stack_info, exc_info=exc_info)


#############
# Exception #
#############
class ServerActionWithWarningsError(UserError):
    """ Exception raised when a server action that has warnings is run. """
    pass
