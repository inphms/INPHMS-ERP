
{
    'name': 'Partners Geolocation',
    'version': '1.0',
    'category': 'Sales/Sales',
    'description': """
Partners Geolocation
========================
    """,
    'depends': ['base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/geo_provider_view.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'data/data.xml',
    ],
    'installable': True,
    'author': 'Inphms Team.',
    'license': 'LGPL-3',
}
