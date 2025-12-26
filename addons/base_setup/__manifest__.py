{
    'name': 'Initial Setup Tools',
    'summary': """
Extension module for Advanced System Configuration at the installation of a new databases, that is not available in base or web module.
    """,
    'version': '1.0',
    'category': 'Hidden',
    'description': """
This module helps to configure the system at the installation of a new database.
================================================================================

Shows you a list of applications features to install from.

    """,
    'depends': ['base', 'web'],
    'data': [
        'data/base_setup_data.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        ],
    'assets': {
        'web.assets_backend': [
            'base_setup/static/src/views/**/*',
        ],
    },
    'auto_install': True,
    'installable': True,

    'author': 'Inphms Team.',
    'license': 'LGPL-3',
}