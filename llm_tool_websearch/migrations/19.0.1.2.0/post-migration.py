# -*- coding: utf-8 -*-
"""Prune orphan xmlids left over from the rename
llm_tool_web_research -> llm_tool_websearch.

Runs once per DB on upgrade to 19.0.1.2.0.
"""

from odoo.addons.llm_tool_websearch.hooks import migrate_cleanup


def migrate(cr, version):
    migrate_cleanup(cr, version)
