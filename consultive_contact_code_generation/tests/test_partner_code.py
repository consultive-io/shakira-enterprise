from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestPartnerCode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.retail = cls.env['partner.sub.type'].create({
            'name': "Retail", 'code': 'ZR',
        })
        cls.wholesale = cls.env['partner.sub.type'].create({
            'name': "Wholesale", 'code': 'ZW',
        })
        cls.customer = cls.env['partner.type'].create({
            'name': "Customer", 'code': 'ZC',
            'partner_sub_type_ids': [(6, 0, (cls.retail | cls.wholesale).ids)],
        })
        cls.vendor = cls.env['partner.type'].create({
            'name': "Vendor", 'code': 'ZV',
            'partner_sub_type_ids': [(6, 0, cls.retail.ids)],
        })
        # No sub types configured, so nothing is allowed under it yet.
        cls.unconfigured = cls.env['partner.type'].create({
            'name': "Unconfigured", 'code': 'ZU',
        })

    def _make_partner(self, name, partner_type=None, sub_type=None, **extra):
        values = {'name': name}
        if partner_type is not None:
            values['partner_type_id'] = partner_type.id
        if sub_type is not None:
            values['partner_sub_type_id'] = sub_type.id
        values.update(extra)
        return self.env['res.partner'].create(values)

    # -- generation ---------------------------------------------------------

    def test_code_generated_with_expected_shape(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        self.assertEqual(partner.partner_code, 'ZCZR000001')
        self.assertEqual(len(partner.partner_code), 10)
        self.assertNotIn('-', partner.partner_code)

    def test_sequence_is_six_digits_and_zero_padded(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        self.assertEqual(partner.partner_code[-6:], '000001')

    def test_sequence_increments_within_a_pair(self):
        first = self._make_partner("First", self.customer, self.retail)
        second = self._make_partner("Second", self.customer, self.retail)
        third = self._make_partner("Third", self.customer, self.retail)
        self.assertEqual(
            [first.partner_code, second.partner_code, third.partner_code],
            ['ZCZR000001', 'ZCZR000002', 'ZCZR000003'],
        )

    def test_sequence_restarts_for_a_different_pair(self):
        """Each type and sub type pair counts on its own."""
        self._make_partner("First", self.customer, self.retail)
        other_sub_type = self._make_partner("Second", self.customer, self.wholesale)
        other_type = self._make_partner("Third", self.vendor, self.retail)
        self.assertEqual(other_sub_type.partner_code, 'ZCZW000001')
        self.assertEqual(other_type.partner_code, 'ZVZR000001')

    def test_equal_prefixes_share_one_counter(self):
        """Segment codes vary in length, so two pairs can spell one prefix.

        Type ``ZAB`` with sub type ``C`` reads the same as type ``ZA`` with sub
        type ``BC``. Sharing a counter is what keeps the codes distinct; drawing
        per pair would hand ``ZABC000001`` to both.
        """
        short_sub = self.env['partner.sub.type'].create({'name': "Short", 'code': 'C'})
        long_sub = self.env['partner.sub.type'].create({'name': "Long", 'code': 'BC'})
        long_type = self.env['partner.type'].create({
            'name': "Long", 'code': 'ZAB',
            'partner_sub_type_ids': [(6, 0, short_sub.ids)],
        })
        short_type = self.env['partner.type'].create({
            'name': "Short", 'code': 'ZA',
            'partner_sub_type_ids': [(6, 0, long_sub.ids)],
        })

        first = self._make_partner("First", long_type, short_sub)
        second = self._make_partner("Second", short_type, long_sub)
        self.assertEqual(first.partner_code, 'ZABC000001')
        self.assertEqual(second.partner_code, 'ZABC000002')
        self.assertNotEqual(first.partner_code, second.partner_code)

    def test_type_offers_only_its_own_sub_types(self):
        """A type with no sub types configured allows none of them."""
        with self.assertRaises(ValidationError):
            self._make_partner("Acme", self.unconfigured, self.wholesale)

    # -- contacts left unclassified -----------------------------------------

    def test_unclassified_contact_is_created_without_a_code(self):
        """Nothing is forced into a catch-all, and nothing is blocked."""
        partner = self._make_partner("Unclassified")
        self.assertFalse(partner.partner_type_id)
        self.assertFalse(partner.partner_sub_type_id)
        self.assertFalse(partner.partner_code)

    def test_classifying_later_issues_the_first_code(self):
        partner = self._make_partner("Unclassified")
        partner.write({
            'partner_type_id': self.customer.id,
            'partner_sub_type_id': self.retail.id,
        })
        self.assertEqual(partner.partner_code, 'ZCZR000001')

    def test_child_contact_does_not_inherit_from_its_parent(self):
        """A child contact is classified in its own dialog, not from the company."""
        company = self._make_partner(
            "Acme", self.customer, self.retail, is_company=True,
        )
        child = self.env['res.partner'].create({
            'name': "Acme Delivery",
            'parent_id': company.id,
            'type': 'delivery',
        })
        self.assertFalse(child.partner_type_id)
        self.assertFalse(child.partner_code)

    def test_child_contact_takes_the_classification_it_is_given(self):
        company = self._make_partner(
            "Acme", self.customer, self.retail, is_company=True,
        )
        child = self.env['res.partner'].create({
            'name': "Acme Delivery",
            'parent_id': company.id,
            'type': 'delivery',
            'partner_type_id': self.vendor.id,
            'partner_sub_type_id': self.retail.id,
        })
        self.assertEqual(child.partner_code, 'ZVZR000001')

    def test_child_contact_draws_its_own_number(self):
        company = self._make_partner(
            "Acme", self.customer, self.retail, is_company=True,
        )
        child = self.env['res.partner'].create({
            'name': "Acme Delivery",
            'parent_id': company.id,
            'partner_type_id': self.customer.id,
            'partner_sub_type_id': self.retail.id,
        })
        self.assertEqual(company.partner_code, 'ZCZR000001')
        self.assertEqual(child.partner_code, 'ZCZR000002')

    # -- half-filled classification -----------------------------------------

    def test_type_without_sub_type_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._make_partner("Acme", self.customer)
        self.assertIn("Partner Sub Type is not set", str(caught.exception))

    def test_sub_type_without_type_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._make_partner("Acme", sub_type=self.retail)
        self.assertIn("Partner Type is not set", str(caught.exception))

    def test_sub_type_outside_the_type_is_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._make_partner("Acme", self.vendor, self.wholesale)
        self.assertIn("not allowed", str(caught.exception))

    # -- reclassification ---------------------------------------------------

    def test_changing_the_type_reissues_the_code(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        self.assertEqual(partner.partner_code, 'ZCZR000001')
        partner.write({'partner_type_id': self.vendor.id})
        self.assertEqual(partner.partner_code, 'ZVZR000001')

    def test_changing_the_sub_type_reissues_the_code(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        partner.write({'partner_sub_type_id': self.wholesale.id})
        self.assertEqual(partner.partner_code, 'ZCZW000001')

    def test_reissue_draws_a_fresh_number(self):
        """The superseded number is not handed back out."""
        partner = self._make_partner("Acme", self.customer, self.retail)
        self._make_partner("Other", self.vendor, self.retail)
        partner.write({'partner_type_id': self.vendor.id})
        self.assertEqual(partner.partner_code, 'ZVZR000002')

    def test_rewriting_the_same_type_keeps_the_code(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        partner.write({'partner_type_id': self.customer.id, 'name': "Acme Ltd"})
        self.assertEqual(partner.partner_code, 'ZCZR000001')

    def test_clearing_the_classification_keeps_the_issued_code(self):
        """The code may already be quoted on an invoice, so it is not withdrawn."""
        partner = self._make_partner("Acme", self.customer, self.retail)
        partner.write({'partner_type_id': False, 'partner_sub_type_id': False})
        self.assertEqual(partner.partner_code, 'ZCZR000001')

    # -- uniqueness ---------------------------------------------------------

    @mute_logger('odoo.sql_db')
    def test_partner_code_is_unique_in_the_database(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        other = self._make_partner("Other", self.customer, self.retail)
        with self.assertRaises(IntegrityError):
            other.with_context(
                allow_partner_code_source_change=True,
            ).write({'partner_code': partner.partner_code})
            self.env.flush_all()

    def test_many_contacts_may_stay_uncoded(self):
        """A partial unique index leaves uncoded contacts out of it entirely."""
        first = self._make_partner("First")
        second = self._make_partner("Second")
        self.env.flush_all()
        self.assertFalse(first.partner_code)
        self.assertFalse(second.partner_code)

    # -- display name -------------------------------------------------------

    def test_display_name_carries_the_code(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        self.assertEqual(partner.display_name, "[ZCZR000001] Acme")

    def test_an_uncoded_contact_reads_as_before(self):
        partner = self._make_partner("Plain")
        self.assertEqual(partner.display_name, "Plain")

    def test_the_code_appears_as_soon_as_one_is_issued(self):
        """The depends must be additive, or the name would go stale."""
        partner = self._make_partner("Later")
        self.assertEqual(partner.display_name, "Later")
        partner.write({
            'partner_type_id': self.customer.id,
            'partner_sub_type_id': self.retail.id,
        })
        self.assertEqual(partner.display_name, "[ZCZR000001] Later")

    def test_a_rename_still_reaches_the_display_name(self):
        """Core's own dependencies must survive the override."""
        partner = self._make_partner("Before", self.customer, self.retail)
        partner.name = "After"
        self.assertEqual(partner.display_name, "[ZCZR000001] After")

    def test_the_company_prefix_core_adds_is_kept(self):
        """Core renders a person as "Company, Person"; the code goes in front."""
        company = self._make_partner(
            "Acme", self.customer, self.retail, is_company=True)
        person = self.env['res.partner'].create({
            'name': "John Doe", 'parent_id': company.id,
            'partner_type_id': self.customer.id,
            'partner_sub_type_id': self.retail.id,
        })
        self.assertEqual(person.display_name, "[ZCZR000002] Acme, John Doe")

    def test_a_contact_is_found_by_its_code_alone(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        found = self.env['res.partner'].name_search('ZCZR000001')
        self.assertIn(partner.id, [record_id for record_id, _label in found])

    def test_a_contact_is_found_by_its_full_display_name(self):
        """An export writes the bracketed form, so it has to read back in."""
        partner = self._make_partner("Acme", self.customer, self.retail)
        found = self.env['res.partner'].name_search(
            partner.display_name, operator='=')
        self.assertIn(partner.id, [record_id for record_id, _label in found])

    def test_the_code_stays_out_of_outbound_email(self):
        """email_formatted is built from name, and must remain so."""
        partner = self._make_partner(
            "Acme", self.customer, self.retail, email='acme@example.com')
        self.assertEqual(partner.email_formatted, '"Acme" <acme@example.com>')
        self.assertNotIn('ZCZR', partner.email_formatted)

    # -- bulk import --------------------------------------------------------

    def _load(self, rows):
        return self.env['res.partner'].load(
            ['name', 'partner_type_id', 'partner_sub_type_id'], rows)

    def test_import_resolves_segments_by_name(self):
        """The form the client types into a spreadsheet."""
        result = self._load([["Imported", "Customer", "Retail"]])
        self.assertFalse(result['messages'], result['messages'])
        partner = self.env['res.partner'].browse(result['ids'])
        self.assertEqual(partner.partner_code, 'ZCZR000001')

    def test_import_resolves_segments_by_code(self):
        result = self._load([["Imported", 'ZC', 'ZR']])
        self.assertFalse(result['messages'], result['messages'])
        self.assertEqual(
            self.env['res.partner'].browse(result['ids']).partner_code, 'ZCZR000001')

    def test_import_accepts_the_form_an_export_writes(self):
        """An export writes display_name, so it has to read back in.

        Without this, a contact list exported from Odoo, edited in a spreadsheet
        and re-imported fails on every row -- the ordinary way bulk data is
        corrected.
        """
        self.assertEqual(self.customer.display_name, '[ZC] Customer')
        result = self._load([["Imported", '[ZC] Customer', '[ZR] Retail']])
        self.assertFalse(result['messages'], result['messages'])
        self.assertEqual(
            self.env['res.partner'].browse(result['ids']).partner_code, 'ZCZR000001')

    def test_import_draws_contiguous_codes_in_bulk(self):
        rows = [["Bulk %s" % i, "Customer", "Retail"] for i in range(25)]
        result = self._load(rows)
        self.assertFalse(result['messages'], result['messages'])
        codes = self.env['res.partner'].browse(result['ids']).mapped('partner_code')
        self.assertEqual(len(set(codes)), 25)
        self.assertEqual(
            sorted(int(code[4:]) for code in codes), list(range(1, 26)))

    def test_import_reports_a_row_missing_its_sub_type(self):
        """The whole file is refused rather than half of it being coded."""
        result = self._load([["Good", "Customer", "Retail"],
                             ["Bad", "Customer", ""]])
        self.assertTrue(result['messages'])
        self.assertIn("Partner Sub Type is not set", str(result['messages']))

    # -- required is a form rule, not a data rule ---------------------------

    def test_required_does_not_block_the_flows_odoo_drives_itself(self):
        """required marks the form; it must not stop Odoo creating contacts.

        Odoo creates a contact with no type in several flows where nobody is
        present to choose one. Those must keep working, so this pins that the
        field being required stays a form rule.
        """
        self.assertTrue(self.env['res.partner']._fields['partner_type_id'].required)
        for label, values in [
            ("plain contact", {'name': "Plain"}),
            ("contact from an email", {'name': "Sender", 'email': 'sender@example.com'}),
            ("child address", {'name': "Ship To", 'type': 'delivery'}),
        ]:
            partner = self.env['res.partner'].create(values)
            self.assertFalse(partner.partner_code, label)
            self.assertFalse(partner.partner_type_id, label)

    def test_required_does_not_block_an_import_without_those_columns(self):
        result = self.env['res.partner'].load(['name'], [["No type column"]])
        self.assertFalse(result['messages'], result['messages'])
        self.assertFalse(self.env['res.partner'].browse(result['ids']).partner_code)

    def test_an_uncoded_contact_can_still_be_edited(self):
        """Legacy contacts predate the module; ordinary writes must not trip."""
        partner = self._make_partner("Legacy")
        partner.write({'phone': '+880 1700 000000', 'name': "Legacy Renamed"})
        self.assertEqual(partner.name, "Legacy Renamed")
        self.assertFalse(partner.partner_code)

    # -- manual generation --------------------------------------------------

    def test_manual_generation_codes_a_contact_that_predates_the_module(self):
        partner = self._make_partner("Legacy")
        partner.with_context(allow_partner_code_source_change=True).write({
            'partner_type_id': self.customer.id,
            'partner_sub_type_id': self.retail.id,
        })
        self.assertFalse(partner.partner_code)
        partner.action_generate_partner_code()
        self.assertEqual(partner.partner_code, 'ZCZR000001')

    def test_manual_generation_is_restricted_to_managers(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        plain_user = self.env['res.users'].create({
            'name': "Plain", 'login': 'plain-partner-code-test',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            partner.with_user(plain_user).action_generate_partner_code()

    # -- copying ------------------------------------------------------------

    def test_duplicating_a_contact_issues_a_new_code(self):
        partner = self._make_partner("Acme", self.customer, self.retail)
        copy = partner.copy()
        self.assertEqual(partner.partner_code, 'ZCZR000001')
        self.assertEqual(copy.partner_code, 'ZCZR000002')
