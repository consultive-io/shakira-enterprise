from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class LastBalanceCommon(AccountTestInvoicingCommon):
    """The standard accounting fixture, runnable next to an item code generator.

    The fixture creates goods with no inventory classification, and an item code
    generator that insists on one (cnslt_item_code_generator) refuses them in
    setUpClass, before a single test runs. Its skip_item_code context key turns
    it off for the test environment; where no such module is installed, the key
    means nothing.
    """

    @classmethod
    def default_env_context(cls):
        return {**super().default_env_context(), 'skip_item_code': True}
