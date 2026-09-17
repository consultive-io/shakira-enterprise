from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestAutoClassification(TransactionCase):
    """The contacts Odoo creates by itself, and the designation that classifies them."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_type = cls.env.ref('consultive_contact_code_generation.partner_type_user')
        cls.user_sub_type = cls.env.ref(
            'consultive_contact_code_generation.partner_sub_type_user')
        cls.employee_type = cls.env.ref(
            'consultive_contact_code_generation.partner_type_employee')
        cls.employee_sub_type = cls.env.ref(
            'consultive_contact_code_generation.partner_sub_type_employee')
        cls.company_type = cls.env.ref(
            'consultive_contact_code_generation.partner_type_company')
        cls.company_sub_type = cls.env.ref(
            'consultive_contact_code_generation.partner_sub_type_company')

    # -- users --------------------------------------------------------------

    def test_new_user_contact_takes_the_user_designation(self):
        user = self.env['res.users'].create({
            'name': "Wilma", 'login': 'wilma-classification-test',
        })
        self.assertEqual(user.partner_id.partner_type_id, self.user_type)
        self.assertEqual(user.partner_id.partner_sub_type_id, self.user_sub_type)
        self.assertTrue(user.partner_id.partner_code.startswith(
            self.user_type.code + self.user_sub_type.code))

    def test_user_designation_wins_over_an_unclassified_contact(self):
        """A plain contact stays blank, so the designation is what sets a user apart."""
        plain = self.env['res.partner'].create({'name': "Plain"})
        user = self.env['res.users'].create({
            'name': "Betty", 'login': 'betty-classification-test',
        })
        self.assertFalse(plain.partner_code)
        self.assertTrue(user.partner_id.partner_code)

    def test_designation_does_not_leak_to_later_contacts(self):
        """The context is handed back stripped, so the next contact is unaffected."""
        users = self.env['res.users'].create([{
            'name': "Barney", 'login': 'barney-classification-test',
        }])
        later = users.env['res.partner'].create({'name': "Later"})
        self.assertFalse(later.partner_type_id)
        self.assertFalse(later.partner_code)

    def test_user_invited_onto_an_existing_contact_keeps_its_code(self):
        contact = self.env['res.partner'].create({
            'name': "Existing",
            'partner_type_id': self.employee_type.id,
            'partner_sub_type_id': self.employee_sub_type.id,
        })
        issued = contact.partner_code
        self.env['res.users'].create({
            'name': "Existing", 'login': 'existing-classification-test',
            'partner_id': contact.id,
        })
        self.assertEqual(contact.partner_code, issued)
        self.assertEqual(contact.partner_type_id, self.employee_type)

    # -- employees ----------------------------------------------------------

    def test_new_employee_work_contact_takes_the_employee_designation(self):
        employee = self.env['hr.employee'].create({'name': "Fred"})
        work_contact = employee.work_contact_id
        self.assertTrue(work_contact)
        self.assertEqual(work_contact.partner_type_id, self.employee_type)
        self.assertEqual(work_contact.partner_sub_type_id, self.employee_sub_type)
        self.assertTrue(work_contact.partner_code.startswith(
            self.employee_type.code + self.employee_sub_type.code))

    def test_employee_linked_to_a_user_keeps_the_user_code(self):
        """The employee takes the user's contact, so no second code is issued."""
        user = self.env['res.users'].create({
            'name': "Pebbles", 'login': 'pebbles-classification-test',
        })
        issued = user.partner_id.partner_code
        employee = self.env['hr.employee'].create({
            'name': "Pebbles", 'user_id': user.id,
        })
        self.assertEqual(employee.work_contact_id, user.partner_id)
        self.assertEqual(user.partner_id.partner_code, issued)
        self.assertEqual(user.partner_id.partner_type_id, self.user_type)

    def test_employee_and_user_codes_count_separately(self):
        first = self.env['hr.employee'].create({'name': "First"})
        second = self.env['hr.employee'].create({'name': "Second"})
        prefix = self.employee_type.code + self.employee_sub_type.code
        self.assertEqual(
            int(second.work_contact_id.partner_code[len(prefix):]),
            int(first.work_contact_id.partner_code[len(prefix):]) + 1,
        )

    # -- companies ----------------------------------------------------------

    def test_new_company_contact_takes_the_company_designation(self):
        company = self.env['res.company'].create({'name': "Slate Rock Gravel"})
        contact = company.partner_id
        self.assertTrue(contact)
        self.assertEqual(contact.partner_type_id, self.company_type)
        self.assertEqual(contact.partner_sub_type_id, self.company_sub_type)
        self.assertTrue(contact.partner_code.startswith(
            self.company_type.code + self.company_sub_type.code))

    def test_branch_contact_takes_the_company_designation(self):
        """A branch is created through the same path, so it is classified too."""
        parent = self.env['res.company'].create({'name': "Bedrock Holdings"})
        branch = self.env['res.company'].create({
            'name': "Bedrock Holdings Quarry", 'parent_id': parent.id,
        })
        self.assertEqual(branch.partner_id.partner_type_id, self.company_type)
        self.assertTrue(branch.partner_id.partner_code)
        self.assertNotEqual(branch.partner_id.partner_code, parent.partner_id.partner_code)

    def test_company_set_up_on_an_existing_contact_keeps_its_code(self):
        contact = self.env['res.partner'].create({
            'name': "Cobblestone Works",
            'is_company': True,
            'partner_type_id': self.employee_type.id,
            'partner_sub_type_id': self.employee_sub_type.id,
        })
        issued = contact.partner_code
        company = self.env['res.company'].create({
            'name': contact.name, 'partner_id': contact.id,
        })
        self.assertEqual(company.partner_id, contact)
        self.assertEqual(contact.partner_code, issued)
        self.assertEqual(contact.partner_type_id, self.employee_type)

    def test_company_designation_does_not_leak_to_later_contacts(self):
        companies = self.env['res.company'].create([{'name': "Rockville Quarry"}])
        later = companies.env['res.partner'].create({'name': "Later"})
        self.assertFalse(later.partner_type_id)
        self.assertFalse(later.partner_code)

    def test_company_is_still_creatable_with_no_designation_configured(self):
        """A missing designation must not make companies impossible to create."""
        self.company_type.auto_assign_to = False
        self.company_sub_type.auto_assign_to = False
        company = self.env['res.company'].create({'name': "Uncoded Quarry"})
        self.assertFalse(company.partner_id.partner_type_id)
        self.assertFalse(company.partner_id.partner_code)

    def test_company_user_and_employee_codes_count_separately(self):
        """Each designation draws on its own prefix, so the counters are distinct."""
        company = self.env['res.company'].create({'name': "Separate Counters Ltd"})
        user = self.env['res.users'].create({
            'name': "Wilma", 'login': 'wilma-company-counter-test',
        })
        employee = self.env['hr.employee'].create({'name': "Fred"})
        prefixes = {
            company.partner_id.partner_code[:-6],
            user.partner_id.partner_code[:-6],
            employee.work_contact_id.partner_code[:-6],
        }
        self.assertEqual(len(prefixes), 3)

    # -- designation configuration ------------------------------------------

    @mute_logger('odoo.sql_db')
    def test_only_one_type_may_hold_a_designation(self):
        with self.assertRaises(IntegrityError):
            self.env['partner.type'].create({
                'name': "Second User Type", 'code': 'ZSU', 'auto_assign_to': 'user',
            })
            self.env.flush_all()

    @mute_logger('odoo.sql_db')
    def test_only_one_sub_type_may_hold_a_designation(self):
        with self.assertRaises(IntegrityError):
            self.env['partner.sub.type'].create({
                'name': "Second User Sub Type", 'code': 'ZSS',
                'auto_assign_to': 'employee',
            })
            self.env.flush_all()

    def test_many_segments_may_hold_no_designation(self):
        """An unset designation is stored as NULL, so blanks do not collide."""
        first = self.env['partner.type'].create({'name': "First", 'code': 'ZNA'})
        second = self.env['partner.type'].create({'name': "Second", 'code': 'ZNB'})
        self.env.flush_all()
        self.assertFalse(first.auto_assign_to)
        self.assertFalse(second.auto_assign_to)

    def test_releasing_a_designation_lets_another_segment_take_it(self):
        self.user_type.auto_assign_to = False
        self.env.flush_all()
        replacement = self.env['partner.type'].create({
            'name': "Replacement", 'code': 'ZRP', 'auto_assign_to': 'user',
            'partner_sub_type_ids': [(6, 0, self.user_sub_type.ids)],
        })
        self.env.flush_all()
        user = self.env['res.users'].create({
            'name': "Dino", 'login': 'dino-classification-test',
        })
        self.assertEqual(user.partner_id.partner_type_id, replacement)

    def test_user_is_still_creatable_with_no_designation_configured(self):
        """A missing designation must not make users impossible to create."""
        self.user_type.auto_assign_to = False
        self.user_sub_type.auto_assign_to = False
        user = self.env['res.users'].create({
            'name': "Bamm-Bamm", 'login': 'bammbamm-classification-test',
        })
        self.assertFalse(user.partner_id.partner_type_id)
        self.assertFalse(user.partner_id.partner_code)

    # -- segment codes ------------------------------------------------------

    def test_code_rejects_digits(self):
        with self.assertRaises(ValidationError):
            self.env['partner.type'].create({'name': "Bad", 'code': 'AB1'})

    def test_code_rejects_punctuation_and_spaces(self):
        for bad in ('A-B', 'A B', 'A_B'):
            with self.assertRaises(ValidationError):
                self.env['partner.type'].create({'name': "Bad", 'code': bad})

    def test_code_rejects_more_than_four_characters(self):
        with self.assertRaises(ValidationError):
            self.env['partner.sub.type'].create({'name': "Bad", 'code': 'ABCDE'})

    def test_code_accepts_one_to_four_letters(self):
        for good in ('Z', 'ZA', 'ZAB', 'ZABD'):
            segment = self.env['partner.sub.type'].create({
                'name': "Good %s" % good, 'code': good,
            })
            self.assertEqual(segment.code, good)

    def test_code_is_uppercased(self):
        segment = self.env['partner.type'].create({'name': "Lower", 'code': 'zlo'})
        self.assertEqual(segment.code, 'ZLO')

    @mute_logger('odoo.sql_db')
    def test_segment_codes_are_unique(self):
        self.env['partner.type'].create({'name': "First", 'code': 'ZDP'})
        with self.assertRaises(IntegrityError):
            self.env['partner.type'].create({'name': "Second", 'code': 'ZDP'})
            self.env.flush_all()

    def test_segment_code_cannot_change_once_codes_are_issued(self):
        partner_type = self.env['partner.type'].create({
            'name': "Locked", 'code': 'ZLK',
            'partner_sub_type_ids': [(6, 0, self.user_sub_type.ids)],
        })
        self.env['res.partner'].create({
            'name': "Coded",
            'partner_type_id': partner_type.id,
            'partner_sub_type_id': self.user_sub_type.id,
        })
        with self.assertRaises(ValidationError) as caught:
            partner_type.code = 'ZLM'
        self.assertIn("cannot be changed", str(caught.exception))

    def test_segment_code_may_change_before_any_code_is_issued(self):
        partner_type = self.env['partner.type'].create({'name': "Free", 'code': 'ZFR'})
        partner_type.code = 'ZFS'
        self.assertEqual(partner_type.code, 'ZFS')
