# -*- coding: utf-8 -*-
"""
views/wizard_steps/__init__.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Package init -- exposes PAGE_FUNCS dict mapping step number -> render callable.
"""
from views.wizard_steps.step1_gene_input       import page as _p1
from views.wizard_steps.step2_host_elements    import page as _p2
from views.wizard_steps.step3_expression_frame import page as _p3
from views.wizard_steps.step4_cloning_primers  import page as _p4
from views.wizard_steps.step5_validation       import page as _p5
from views.wizard_steps.step6_export           import page as _p6

PAGE_FUNCS = {
    1: _p1,
    2: _p2,
    3: _p3,
    4: _p4,
    5: _p5,
    6: _p6,
}

__all__ = ["PAGE_FUNCS"]
