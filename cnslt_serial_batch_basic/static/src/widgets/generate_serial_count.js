import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
import { GenerateDialog } from "@stock/widgets/generate_serial";

/**
 * Number of SN follows the quantity being received.
 *
 * Core fills that box from the line's Demand. On a receipt the quantity column
 * is the truer count: it is what actually turned up, and short deliveries are
 * ordinary. Numbering to Demand there issues serials for units nobody received,
 * which then have to be deleted line by line before the receipt will validate.
 *
 * Demand stays the fallback, for the case core already handled: a line whose
 * quantity is still zero.
 *
 * Registered after super.setup(), so this onMounted runs after core's and its
 * value is the one left in the box. Serial tracking only -- under lot tracking
 * the same box means "quantity per lot", which this would make nonsense of.
 */
patch(GenerateDialog.prototype, {
    setup() {
        super.setup();
        onMounted(() => {
            if (this.props.mode !== "generate") {
                return;
            }
            const move = this.props.move.data;
            if (move.has_tracking !== "serial" || move.picking_code !== "incoming") {
                return;
            }
            if (move.quantity) {
                this.nextSerialCount.el.value = move.quantity;
            }
        });
    },
});
