from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestSerialBatch(TransactionCase):
    """The batch layer: where a unit's date and warranty live.

    Serial numbers carry no date of their own, so everything about a unit's age
    is read off the batch it belongs to.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.finished_goods = cls.env['inventory.category'].create({
            'name': "Finished Goods", 'code': 'ZF',
        })
        cls.home_appliance = cls.env['inventory.type'].create({
            'name': "Home Appliance", 'code': 'ZH',
        })
        cls.induction = cls.env['product.category'].create({
            'name': "Induction", 'code': 'ZI',
        })
        cls.flat_top = cls.env['product.category'].create({
            'name': "Flat Top", 'code': 'ZT', 'parent_id': cls.induction.id,
        })
        cls.product = cls._make_product("Cooker")
        cls.other_product = cls._make_product("Griddle")
        cls.today = date.today()

    @classmethod
    def _make_product(cls, name, **extra):
        values = {
            'name': name,
            'is_storable': True,
            'inventory_category_id': cls.finished_goods.id,
            'inventory_type_id': cls.home_appliance.id,
            'categ_id': cls.flat_top.id,
        }
        values.update(extra)
        return cls.env['product.template'].create(values)

    def _make_batch(self, product=None, **extra):
        values = {
            'product_id': (product or self.product).product_variant_id.id,
            'date': self.today,
            'source_type': 'receipt',
        }
        values.update(extra)
        return self.env['inventory.serial.batch'].create(values)

    def _make_lot(self, name, product=None, **extra):
        values = {
            'name': name,
            'product_id': (product or self.product).product_variant_id.id,
            'company_id': self.env.company.id,
        }
        values.update(extra)
        return self.env['stock.lot'].create(values)

    # -- naming -------------------------------------------------------------

    def test_name_is_drawn_from_the_sequence(self):
        batch = self._make_batch()
        self.assertTrue(
            batch.name.startswith("BATCH/%s/" % self.today.year),
            "unexpected batch name: %s" % batch.name,
        )
        self.assertNotEqual(batch.name, "New")

    def test_names_are_distinct(self):
        names = {self._make_batch().name for _ in range(3)}
        self.assertEqual(len(names), 3)

    # -- warranty -----------------------------------------------------------

    def test_warranty_end_date_is_the_date_plus_the_term(self):
        batch = self._make_batch(date=date(2026, 1, 31), warranty_months=12)
        self.assertEqual(batch.warranty_end_date, date(2027, 1, 31))

    def test_no_warranty_leaves_the_end_date_empty(self):
        """Zero months is 'no warranty', not a term expiring the day it began."""
        batch = self._make_batch(warranty_months=0)
        self.assertFalse(batch.warranty_end_date)

    def test_warranty_survives_a_later_change_to_the_product(self):
        """The batch snapshots the term, so units already sold keep what they
        were sold under."""
        self.product.default_warranty_months = 24
        batch = self._make_batch(warranty_months=self.product.default_warranty_months)
        self.assertEqual(batch.warranty_months, 24)

        self.product.default_warranty_months = 6

        self.assertEqual(batch.warranty_months, 24)
        self.assertEqual(batch.warranty_end_date, self.today + relativedelta(months=24))

    def test_negative_warranty_is_refused(self):
        with self.assertRaises(ValidationError):
            self._make_batch(warranty_months=-1)

    def test_negative_warranty_on_the_product_is_refused(self):
        with self.assertRaises(ValidationError):
            self.product.default_warranty_months = -1

    # -- dates --------------------------------------------------------------

    def test_a_future_date_is_refused(self):
        """A batch records goods that have arrived, not goods that will."""
        with self.assertRaises(ValidationError):
            self._make_batch(date=self.today + timedelta(days=1))

    # -- lots ---------------------------------------------------------------

    def test_lots_of_another_product_are_refused(self):
        batch = self._make_batch()
        stray = self._make_lot("ZIZT002000001", product=self.other_product)

        with self.assertRaises(ValidationError):
            batch.lot_ids = stray

    def test_a_stray_lot_is_refused_from_the_lot_side_too(self):
        """Work item 5 attaches serials by writing ``batch_id`` on the lot, not by
        pushing ``lot_ids`` from the batch, so the guard has to hold on that path."""
        batch = self._make_batch()
        stray = self._make_lot("ZIZT002000001", product=self.other_product)

        with self.assertRaises(ValidationError):
            stray.batch_id = batch
            self.env.flush_all()

    def test_lot_count_follows_the_lots(self):
        batch = self._make_batch()
        self.assertEqual(batch.lot_count, 0)

        batch.lot_ids = (
            self._make_lot("ZIZT001000001") + self._make_lot("ZIZT001000002")
        )

        self.assertEqual(batch.lot_count, 2)

    def test_warranty_reaches_the_lot(self):
        """Stored on the lot so warranty reports can filter and sort on it."""
        batch = self._make_batch(warranty_months=12)
        lot = self._make_lot("ZIZT001000001", batch_id=batch.id)

        self.assertEqual(lot.warranty_end_date, batch.warranty_end_date)
        self.assertTrue(lot.warranty_end_date)

    # -- deletion -----------------------------------------------------------

    def test_deleting_a_batch_with_serials_is_refused(self):
        """The units are in customers' hands; their warranty terms live here."""
        batch = self._make_batch()
        self._make_lot("ZIZT001000001", batch_id=batch.id)

        with self.assertRaises(UserError):
            batch.unlink()

    def test_an_empty_batch_can_be_deleted(self):
        batch = self._make_batch()
        batch.unlink()
        self.assertFalse(batch.exists())

    @mute_logger('odoo.sql_db')
    def test_the_database_refuses_it_too(self):
        """``ondelete='restrict'`` backs the unlink guard up with a foreign key, so
        a deletion that never runs our Python -- raw SQL, or a cascade from
        somewhere else -- is still refused."""
        batch = self._make_batch()
        self._make_lot("ZIZT001000001", batch_id=batch.id)
        self.env.flush_all()

        with self.assertRaises(IntegrityError):
            with self.cr.savepoint():
                self.env.cr.execute(
                    "DELETE FROM inventory_serial_batch WHERE id = %s", (batch.id,),
                )
