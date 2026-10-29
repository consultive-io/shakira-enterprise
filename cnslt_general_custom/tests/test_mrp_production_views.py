# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMrpProductionViews(TransactionCase):
    """Test MRP production form view customizations."""

    def test_mrp_production_custom_view_applied(self):
        """Verify inherited view is loaded and arch contains required attributes."""
        custom_view = self.env.ref('cnslt_general_custom.mrp_production_form_view_custom')
        self.assertTrue(custom_view.exists())
        self.assertEqual(custom_view.inherit_id, self.env.ref('mrp.mrp_production_form_view'))

        # Check fields view get includes the customizations
        form_arch = self.env['mrp.production'].get_view(view_id=custom_view.id, view_type='form')['arch']
        self.assertIn('action_cancel', form_arch)
        self.assertIn('move_raw_ids', form_arch)
