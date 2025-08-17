{
    'name': 'Learning Agreement Demo',
    'summary': 'Learning Agreement workflow: student portal form, coordinator fields, document generation, signatures, reminders, and chat',
    'version': '18.0.1.0.0',
    'category': 'Education',
    'author': 'Project Setup by Assistant',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'depends': [
        'base',
        'mail',
        'portal',
        'website',
        'auth_signup',
        'sign'
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'views/menus.xml',
        'views/learning_agreement_views.xml',
        'views/res_config_settings_views.xml',
        'views/portal_templates.xml',
        'views/portal_assets.xml',
        'report/learning_agreement_report.xml',
        'data/mail_templates.xml',
        'data/ir_cron.xml'
    ],
    'assets': {
    },
}