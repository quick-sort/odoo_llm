# -*- coding: utf-8 -*-
{
    'name': 'LLM Screening',
    'version': '1.0.0',
    'category': 'Business Development',
    'summary': 'Profile-driven screening of arbitrary records with LLM evaluation',
    'description': """
LLM Screening
=============
Generic screening framework. A screen.profile bundles a description with a list
of rules (screen.profile.rule). A screen.result attaches an evaluation to any
record via the attachment-style res_model/res_id pair, with one
screen.result.item per rule.
    """,
    'author': 'Harbour BioMed',
    'website': 'https://www.harbourbiomed.com',
    'depends': ['llm_assistant'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/llm_assistant_screening_data.xml',
        'views/screen_profile_views.xml',
        'views/screen_result_views.xml',
        'views/screen_menu.xml',
    ],
    'demo': [
        'demo/screen_profile_demo.xml',
        'demo/screen_result_demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
