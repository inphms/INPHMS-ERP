
{
    'name': 'Web Routing',
    'summary': 'Extension module for advanced HTTP routing that is not available in base or web module.',
    'sequence': 9100,
    'category': 'Hidden',
    'description': """
Proposes advanced routing options not available in web or base to keep
base modules simple.
""",
    'data': [
        'views/http_routing_template.xml',
        'views/res_lang_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'depends': ['web'],
    'author': 'Inphms Team.',
    'license': 'LGPL-3',
}
