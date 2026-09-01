# Automatic Account Code Generation — User Guide

This module generates chart of accounts codes for you, so that codes stay
consistent and nobody has to remember which number comes next.

---

## The idea in one line

Pick the group an account belongs to, and Odoo writes the code for you.

If the group **Bank** uses the prefix `10102`, the accounts you create under it
will be numbered `10102001`, `10102002`, `10102003`, and so on.

---

## One-time setup

### Step 1 — Set the serial length

Go to **Accounting → Configuration → Settings**, find the block
**Chart of Accounts Coding**.

- **Serial Width** — how many digits are reserved at the end of the code for the
  running number. `3` gives you `001` to `999` under each group. This is the
  normal choice.
- **Enforce Automatic Coding** — tick this once you are confident in your setup.
  It stops users from typing codes by hand on new accounts.

### Step 2 — Prepare your groups

Go to **Accounting → Configuration → Account Groups**.

Each group already has a code prefix (this is standard Odoo). The module adds
three fields:

| Field | What it does |
|---|---|
| **Allow Auto Coding** | Untick on high-level summary groups (like "Assets") so they don't appear in the dropdown. Leave ticked on the groups you actually file accounts under. |
| **Coding Prefix** | The prefix used for generating codes. It fills itself from the group's starting prefix — only change it if the group covers a range and you want codes issued under one specific number. |
| **Serial Width** | Overrides the company setting for this group only. Leave at `0` to use the company default. |
| **Next Code** | Shows you what the next account under this group will be numbered. Read-only. |

**Rule of thumb:** tick *Allow Auto Coding* only on your lowest-level groups. If
a group has sub-groups beneath it, file accounts under the sub-groups instead.

---

## Day-to-day use

### Creating a new account

1. Go to **Accounting → Configuration → Chart of Accounts** and click **New**.
2. Type the account name.
3. Open the **Accounting** tab. Leave **Coding Mode** on *Automatic*.
4. Choose the **Coding Group**.
5. The code appears immediately as a preview.
6. Save.

The code you see before saving is a preview. If a colleague creates an account
under the same group at the same moment, the saved code may be one higher than
the preview showed. This is normal and means the system is protecting you from
duplicates.

### Entering a code by hand

Set **Coding Mode** to *Manual*. The code field then behaves exactly as it does
in standard Odoo. Use this for one-off accounts that don't fit your numbering
scheme.

If *Enforce Automatic Coding* is switched on in Settings, the Manual option is
not available for new accounts.

### Fixing a code you don't like

If the account has **no journal entries yet**, open it and click the
**Regenerate Code** button at the top right. It issues the next available number
for the group, ignoring the account's own current code.

In practice this means:

- If the account is the newest one in its group, the code stays as it is. The
  button is safe to click repeatedly.
- If you moved the account to a different group, it gets a fresh code under the
  new group's prefix.
- If the account sits in the middle of a sequence, it moves to the end of that
  group's numbering. Its old number is not given to anyone else.

If the account already has journal entries, the button is hidden. Codes on
accounts with posted transactions are not changed — that would break your audit
trail. Create a new account instead and archive the old one.

---

## What happens to your existing accounts

Nothing changes. When the module is installed it looks at every account you
already have, records which group its code belongs to, and marks it as
*Manual*. No existing code is touched, no report changes, no entry is affected.

You can switch any existing account to *Automatic* later if you want, but there
is usually no reason to.

---

## Messages you might see

**"Prefix 10102 is exhausted: all 999 serials are in use."**
You have filled every number under that group. Either raise the Serial Width for
that group, or split it into sub-groups.

**"The generated code would be reported under group X instead of Y."**
The group you selected has a sub-group whose prefix range overlaps the numbers
being generated. File the account under the sub-group instead, or untick
*Allow Auto Coding* on the parent group.

**"The coding prefix can only contain alphanumeric characters and dots."**
Odoo does not allow dashes, spaces or symbols in account codes. Use digits,
letters or dots only.

---

## Things worth knowing

- **Numbers are never reused.** If you delete account `10102002`, the next
  account will still be `10102003`. Gaps in the numbering are intentional and
  make your history easier to audit.
- **Each group counts separately.** Filling up *Bank* has no effect on *Cash*.
- **Multi-company.** If you run several companies, each one keeps its own
  numbering. An account shared between companies gets a correct code in each.
- **Imports are untouched.** Importing a chart of accounts from a spreadsheet
  works exactly as before; the module stays out of the way.

---

## Getting help

Contact Consultive at support@consultive.io with your Odoo version, the account
or group you were working on, and the exact message shown on screen.
