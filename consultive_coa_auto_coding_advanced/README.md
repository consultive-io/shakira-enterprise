# Chart of Accounts Auto Coding — Account Types (`consultive_coa_auto_coding_advanced`)

Odoo 19.0. Depends on `consultive_coa_auto_coding_basic`, which is **not modified** by
this module.

## What it does

Adds the level above the account group. Codes become a three-level scheme:

```
account type   06         two digits, configured once
account group  06001      five digits: type code + running serial
account        06001001   eight digits: group prefix + running serial
```

The bottom level is `_basic`'s existing behaviour; this module generates the middle one
and configures the top.

## Design notes

* **Why a wrapper model.** `account.account.account_type` is a Selection of 19 hardcoded
  values, so there is nowhere to store a code against it. `caac.account.type` holds
  exactly one record per selection value — a complete mirror, not a curated subset — and
  carries the two-digit code. Selecting the wrapper fills the standard type, so the two
  cannot drift apart.
* **Seeded, not hand-built.** `post_init_hook` walks the *live* selection and creates any
  missing record, so values added by a future Odoo version or another module appear
  without this module being touched. It is idempotent, so a migration script can re-run
  it. Codes are left blank: filling them in is the one-time configuration.
* **Global record, per-company code.** `account.account.company_ids` is a Many2many, so an
  account can span two company trees; a per-company wrapper record would be ambiguous as a
  Many2one target. The record is therefore global while `code` is `company_dependent`,
  which keeps codes per root company. Consequence: code uniqueness per company is a Python
  constraint, because a company-dependent field lives in JSONB and cannot carry a unique
  index.
* **Core's type compute is deliberately untouched.** `_compute_account_type` infers the
  type from the closest parent account by code prefix and is what chart-template
  installation depends on. This module fills `account_type` through an onchange and a
  `create` override instead, and only when it was not supplied. `account_type` stays
  writable at ORM level, so imports and chart templates behave exactly as before.
* **No reverse compute.** The wrapper is never derived from `account_type`; that would
  risk a compute cycle. Existing accounts are backfilled once at install, which is
  unambiguous because `account_type` is unique across wrapper records.
* **Prefix fields are written together.** A generated group code lands on
  `code_prefix_start`, `code_prefix_end` and `_basic`'s `coding_prefix` at once. Core has a
  database constraint that start and end be the same length, which one shared value
  satisfies, and core recomputes the group's `parent_id` from the prefixes by itself.
* **Codes are frozen once used.** A type's code cannot change once groups have been coded
  from it, and a group's type cannot change once accounts carry codes under its prefix.
  Both would otherwise leave records with a code that no longer matches their
  classification. The check mirrors `_code_is_in_use()` in `cnslt_item_code_generator`.

## Known limitation — shared with `_basic`

Serial allocation takes `pg_advisory_xact_lock` and then re-reads the codes already
issued. Odoo runs every cursor at `REPEATABLE READ`, so that re-read uses a snapshot fixed
at or before the blocking lock statement and **cannot see the transaction that just
released the lock**. Two simultaneous creations under one prefix can therefore be handed
the same serial. Core's `_ensure_code_is_unique` reads under the same stale snapshot and
will not catch it.

This is a pre-existing defect in `_basic` that this module's group allocator inherits, and
it was consciously deferred. Because `_basic` was left untouched, **the eventual fix
applies in two places**: `_basic`'s `_caac_build_code`, and
`caac.serial.allocator.mixin` here. The arithmetic is isolated in that mixin specifically
so `_basic` can adopt it when the fix is made.

The practical exposure is low — it needs two users creating accounts under the same prefix
in the same instant — but it is not zero, and it should not be described as solved.

## Deferred

* **Customization 1.2** — filtering the Coding Group dropdown on the account form by
  account type. The wrapper reduces this to a one-line domain:
  `[('coding_allowed','=',True), ('caac_account_type_id','=',caac_account_type_id)]`
* Adopting existing groups (e.g. `60201`) into the type scheme. Only new groups are coded;
  existing prefixes are left alone.
* A custom OWL widget reproducing the grouped Balance Sheet / P&L sections of core's
  `account_type_selection`. That widget only binds to Selection fields, so the wrapper uses
  a plain Many2one whose `sequence` reproduces the same reading order instead.
