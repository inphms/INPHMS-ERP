{
    'name': 'Mobile',
    "summary": "Extension module for advanced Mobile App that is not available in base or web module.",
    'category': 'Hidden',
    'description': """
Inphms Mobile Core module.
========================

This module provides the core of the Inphms Mobile App.
""",
    'depends': ['web'],
    'auto_install': True,
    'data': [
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_mobile/static/src/js/**/*',
            'web_mobile/static/src/views/**/*',
        ],
    },
    'author': 'Inphms Team.',
    'license': 'LGPL-3',
}