{
    'name': 'AI',
    'description': """
Base Inphms AI Features module.
===============================================

AI-related features are accessible with limited configurability.
    """,
    'version': '1.0',
    'category': 'Hidden/Tools',
    'auto_install': False,
    'depends': ['mail',],
    'data': [
        'data/ir_actions_server_data.xml',
        'data/ai_topic_data.xml',
        'data/ai_agent_data.xml',
        'security/ir.model.access.csv',
        'views/ai_log_action.xml',
        'views/ir_actions_server_views.xml',
        'wizard/mail_compose_message_views.xml',
        'views/mail_scheduled_message_views.xml',
        'views/mail_template_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'bootstrap': True,
    'assets': {
        'web.assets_backend': [
            ('after', 'web/static/src/views/form/form_controller.js',
                'ai/static/src/web/form_controller_patch.js'),
            'ai/static/src/ai_chat_launcher_service.js',
            'ai/static/src/**/*',
            ('remove', 'ai/static/src/worklets/**/*')
        ],
    },
    'author': 'Inphms Team.',
    'license': 'LGPL-3',
}