# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Remove stale lot restriction views from the database before views are loaded.
    Commit 619383b added picking_has_purchase_id to stock.move and modified these
    views in the database. When that commit was reverted, the field was removed from
    Python, causing view validation to fail when loading views inheriting
    stock.view_picking_form prior to lot_restriction_views.xml being processed.
    Deleting the stale views allows Odoo to cleanly recreate them from XML.
    """
    if not version:
        return

    _logger.info("cnslt_serial_batch_basic: cleaning up stale lot lock views before upgrade...")
    cr.execute("""
        DELETE FROM ir_ui_view
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'cnslt_serial_batch_basic'
              AND model = 'ir.ui.view'
              AND name IN (
                  'view_picking_form_lot_lock',
                  'view_move_line_operation_lot_lock',
                  'view_move_line_detailed_operation_lot_lock',
                  'view_move_line_form_lot_lock'
              )
        );
        DELETE FROM ir_model_data
        WHERE module = 'cnslt_serial_batch_basic'
          AND model = 'ir.ui.view'
          AND name IN (
              'view_picking_form_lot_lock',
              'view_move_line_operation_lot_lock',
              'view_move_line_detailed_operation_lot_lock',
              'view_move_line_form_lot_lock'
          );
    """)
