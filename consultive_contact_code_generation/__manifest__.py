{
    'name': "Contact Code Generation",
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': "Generate segmented partner codes from a partner type and sub type",
    'description': """
Contact Code Generation
=======================

Assembles a code from a partner's classification plus a running sequence, and
writes it to the contact as a Partner Code::

    Partner Code:  [TYPE][SUB TYPE][SEQUENCE]
                    CUS    RTL      000001    ->  CUSRTL000001

Type and sub type codes are alphabetic and at most four characters, so the code
is as long as they make it; the sequence is always six digits.

A contact is classified by hand -- on the contact form, in the quick-create
dialog, and in the Contact / Address dialog for a child contact or address --
and the code is issued when it is saved. A contact nobody has classified stays
blank, and is coded as soon as someone assigns a type to it.

Three situations have no one present to classify the contact, because Odoo
creates it by itself. Each has a type and sub type nominated ahead of time:

* the pair designated for **Users**, for the contact behind a new ``res.users``;
* the pair designated for **Employees**, for an employee's work contact;
* the pair designated for **Companies**, for the contact behind a new
  ``res.company``, a branch included.

Exactly one type and one sub type may hold each designation, which is enforced by
a unique index rather than left to convention. A record Odoo links to a contact
that already exists keeps the code that contact was issued: an employee linked to
a user takes that user's contact and stays coded under Users, and a company set
up on an existing contact keeps that contact's code.
""",
    'author': "Consultive",
    'website': 'https://consultive.io',
    'license': 'LGPL-3',
    'depends': ['contacts', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'data/partner_type_data.xml',
        'views/partner_type_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
