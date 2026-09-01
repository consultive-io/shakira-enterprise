from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

SEQUENCE_MAX = 999
SEQUENCE_PADDING = 3
SEQUENCE_CODE_PREFIX = 'inventory.item.code.'

# Changing any of these after a code has been issued would leave the product
# carrying a code that no longer describes it.
SOURCE_FIELDS = ('inventory_category_id', 'inventory_type_id', 'categ_id')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    inventory_category_id = fields.Many2one(
        'inventory.category', string="Inventory Category", index=True,
        help="First segment of the item code.",
    )
    inventory_type_id = fields.Many2one(
        'inventory.type', string="Inventory Type", index=True,
        help="Second segment of the item code.",
    )
    item_code = fields.Char(
        readonly=True, copy=False, index=True, tracking=True,
        help="Inventory Category + Inventory Type + product category parent + "
             "child + sequence. The Inventory Category and Type codes are "
             "free-length, so the item code is as long as they make it; its "
             "last 7 characters are always the Internal Reference.",
    )
    # A superseded code may already be printed on labels and purchase orders, so
    # every reissue has to stay traceable on the record.
    default_code = fields.Char(tracking=True)

    # -- generation ---------------------------------------------------------

    def _item_code_applies(self):
        """Only goods are classified. Services and combos carry no inventory."""
        self.ensure_one()
        if self.env.context.get('skip_item_code'):
            return False
        return self.type == 'consu'

    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        for template in templates:
            if template._item_code_applies() and not template.item_code:
                template._generate_item_code()
        return templates

    def _generate_item_code(self):
        self.ensure_one()
        self._check_classification_ready()
        scope = self.categ_id.parent_id.code + self.categ_id.code
        sequence = self._draw_sequence(scope)
        self.with_context(allow_item_code_source_change=True).write({
            'item_code': (
                self.inventory_category_id.code
                + self.inventory_type_id.code
                + scope
                + sequence
            ),
            'default_code': scope + sequence,
        })

    def _check_classification_ready(self):
        """Refuse to generate a partial code rather than skipping silently."""
        self.ensure_one()
        problems = []
        if not self.inventory_category_id:
            problems.append(_("Inventory Category is not set."))
        if not self.inventory_type_id:
            problems.append(_("Inventory Type is not set."))

        category = self.categ_id
        if not category:
            problems.append(_("Product Category is not set."))
        elif not category.parent_id:
            problems.append(_(
                "Product Category \"%(name)s\" is a top-level category. Products must "
                "be assigned to a child category.",
                name=category.display_name,
            ))
        else:
            if not category.parent_id.code:
                problems.append(_(
                    "Product Category \"%(name)s\" has no code.",
                    name=category.parent_id.display_name,
                ))
            if not category.code:
                problems.append(_(
                    "Product Category \"%(name)s\" has no code.",
                    name=category.display_name,
                ))

        if problems:
            raise ValidationError(_(
                "An item code cannot be generated for \"%(product)s\":\n%(problems)s",
                product=self.display_name or _("this product"),
                problems="\n".join("  - %s" % problem for problem in problems),
            ))

    # -- sequence -----------------------------------------------------------

    @api.model
    def _draw_sequence(self, scope):
        """Draw the next number for a PC+SC scope.

        Scoping to PC+SC is what makes the Internal Reference unique: only one
        product can ever hold a given (parent, child, sequence) triple. Scoping it
        any wider would let two products in different Category/Type combinations
        both reach 001 and produce the same Internal Reference.
        """
        sequence = self._get_sequence(scope)
        if sequence.number_next_actual > SEQUENCE_MAX:
            raise UserError(self._exhausted_message(scope))
        value = sequence.next_by_id()
        if int(value) > SEQUENCE_MAX:
            raise UserError(self._exhausted_message(scope))
        return value

    @api.model
    def _get_sequence(self, scope):
        code = SEQUENCE_CODE_PREFIX + scope
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([('code', '=', code)], limit=1)
        if not sequence:
            sequence = Sequence.create({
                'name': _("Item Code - %s", scope),
                'code': code,
                # no_gap takes a row lock, which serialises concurrent draws and is
                # what makes the 999 ceiling reliable.
                'implementation': 'no_gap',
                'padding': SEQUENCE_PADDING,
                'number_next': 1,
                'number_increment': 1,
                'company_id': False,
            })
        return sequence

    @api.model
    def _exhausted_message(self, scope):
        return _(
            "The item code sequence for product category %(scope)s is exhausted: "
            "all %(maximum)s numbers have been issued. A new child category is "
            "needed for further products.",
            scope=scope,
            maximum=SEQUENCE_MAX,
        )

    # -- protection ---------------------------------------------------------

    def write(self, vals):
        changed = [name for name in SOURCE_FIELDS if name in vals]
        if changed and not self.env.context.get('allow_item_code_source_change'):
            for template in self:
                if not template.item_code:
                    continue
                for name in changed:
                    if template[name].id != vals[name]:
                        raise UserError(_(
                            "%(field)s cannot be changed on \"%(product)s\": item code "
                            "%(code)s was generated from it and is never recomputed. "
                            "To reclassify this product, archive it and create a "
                            "replacement under the correct classification.",
                            field=self._fields[name].string,
                            product=template.display_name,
                            code=template.item_code,
                        ))
        return super().write(vals)

    def action_regenerate_item_code(self):
        """Reissue a code from the current classification. Corrections only."""
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_(
                "Only Inventory Managers may regenerate item codes."
            ))
        for template in self:
            template._generate_item_code()
