# Account Type Coding — User Guide

This module numbers your account groups for you, so that the whole chart of accounts
follows one consistent pattern from the top down.

---

## The idea in one line

Give each account type a two-digit code once, and every group and account below it is
numbered automatically.

```
Account type   Expenses            06
Account group  Office Expense      06001
Account group  Factory Expense     06002
Account        Office supplies     06001001
Account        Office marketing    06001002
```

The type code is the first two digits of everything beneath it, so you can tell what an
account is just by reading its number.

---

## One-time setup

Go to **Accounting → Configuration → Account Type Coding**.

You will find one line for every account type Odoo has — Receivable, Bank and Cash,
Current Assets, Expenses, and so on. You do not create these; they are already there.

Type a **two-digit code** next to each type you plan to use. Types with no code yet are
highlighted, so you can see at a glance what is left to do.

You only have to code the types you actually file accounts under. If you never create
groups for *Off-Balance Sheet*, leave it blank.

**Choose these codes carefully.** Once you have created groups under a type, its code is
locked — changing it would leave every group and account below it carrying a number that
no longer matches. If you genuinely need to change one, the groups have to go first.

---

## Day-to-day use

### Creating an account group

1. Go to **Accounting → Configuration → Account Groups** and click **New**.
2. Type the group name, for example *Office Expense*.
3. Choose the **Account Type**.
4. The code prefix fills in by itself — `06001` — and is greyed out.
5. Save.

The next group you create under *Expenses* becomes `06002`, then `06003`, and so on. Each
type counts separately, so filling up *Expenses* has no effect on *Income*.

If the type has no code yet, you will be told so and pointed at the configuration screen.
Set the code, then create the group.

### Creating an account

Unchanged from before, except that the account form now leads with **Account Type**:

1. **Accounting → Configuration → Chart of Accounts → New**.
2. Type the account name.
3. Choose the **Account Type** — the standard *Type* field below it fills in to match and
   turns grey, so you can always see what Odoo itself is using for reports.
4. Choose the **Coding Group**.
5. The code appears — `06001001`.
6. Save.

### Changing a group's type

Allowed only while no accounts have been created under the group. The group is renumbered
under the new type: a group that was `06001` becomes `04001` if you move it to *Income*.

Once accounts exist under the group, the type is locked. Those accounts already carry
codes built from the old prefix, and renumbering them is an audit decision rather than a
technical one. Create a new group instead and archive the old one.

---

## What happens to your existing data

**Nothing is renumbered.** Groups you already have keep their prefixes, and no account
code changes. The module only records which account type each existing account already
belongs to, so the new fields are filled in and consistent from day one.

New groups you create from now on will be numbered under the type scheme. If you want
older groups brought into the same scheme, that is a separate exercise — ask us.

---

## Messages you might see

**"Account type Expenses has no code for My Company yet."**
Go to **Accounting → Configuration → Account Type Coding** and give that type a two-digit
code, then create the group again.

**"The code of Expenses cannot be changed: account groups have already been coded from it."**
Groups `06001`, `06002`… already exist. Their numbers were built from `06` and would stop
making sense. Delete or re-file those groups first if the code really must change.

**"Code 06 is already used by Income in this company."**
Two account types cannot share a code, or their group numbers would collide. Pick another.

**"The code of Expenses must be exactly 2 digits."**
Two digits, no more, no less — `06`, not `6` or `060`. Every group code below it is five
characters, and that only works if the type code is a fixed width.

**"Prefix 06 is exhausted: all 999 serials are in use."**
You have created 999 groups under one account type. Split it, or talk to us about widening
the serial.

---

## Things worth knowing

- **Numbers are never reused.** Delete group `06002` and the next one is still `06003`.
  Gaps are intentional and make history easier to audit.
- **Multi-company.** Each company keeps its own two-digit codes for the same account type,
  so companies can number their charts differently.
- **Imports are untouched.** Importing a chart of accounts from a spreadsheet works exactly
  as before; the module stays out of the way.
- **Reports are unaffected.** The standard Odoo account type still drives every report. The
  new field only decides what the codes look like.

---

## Getting help

Contact Consultive at support@consultive.io with your Odoo version, the account type,
group or account you were working on, and the exact message shown on screen.
