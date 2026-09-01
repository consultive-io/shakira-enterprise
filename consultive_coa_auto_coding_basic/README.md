# Chart of Accounts Auto Coding (`consultive_coa_auto_coding_basic`)

Odoo 19.0 — Community and Enterprise. Single dependency: `account`.

## What it does

Adds a **Coding Group** selector to the account form. When an account is saved in
`auto` mode, its code is generated as:

    <group coding prefix> + <zero-padded serial>

e.g. group *Bank* with prefix `10102` and a serial width of 3 yields `10102001`,
`10102002`, …

## Design notes

* **Direction of truth.** Standard Odoo derives `group_id` *from* the code. This
  module adds a separate stored `coding_group_id` that drives the code, and then
  asserts the generated code resolves back to the selected group. Core behaviour
  is untouched, and there is no compute cycle.
* **Company-dependent codes.** In 19.0 `account.account.code` is a non-stored
  compute over `code_store`, a company-dependent JSONB keyed by *root* company.
  Serial lookup therefore runs as raw SQL on `code_store ->> '<root_company_id>'`,
  and codes are allocated for every company on the account.
* **Concurrency.** Core enforces code uniqueness in Python (`_ensure_code_is_unique`),
  not via a database constraint. Allocation is wrapped in
  `pg_advisory_xact_lock(root_company_id, hashtext(prefix))`, which serialises
  per prefix without blocking unrelated prefixes.
* **No gap reuse.** The next serial is always `max + 1`. Reusing freed numbers
  looks tidy and causes audit confusion.
* **Overflow blocks.** When a prefix exhausts its serial width, creation raises
  rather than silently widening the code.
* **Existing data.** `post_init_hook` backfills `coding_group_id` from each
  account's current code and sets existing accounts to manual mode. No existing
  code is modified.

## Escape hatches

* Per-account `coding_mode = manual` restores stock behaviour.
* Context flag `caac_no_autocode=True` disables generation (used by imports).
* `import_file` context is skipped automatically.

## Known limitation

`Enforce Automatic Account Coding` is enforced through the form view (mode locked,
group required) rather than a Python constraint. A server-side constraint would
break chart-template installation, which creates accounts with explicit codes and
no coding group.

## Deferred to v2

* Bulk renumbering wizard (rewriting codes on accounts with journal items is an
  audit decision).
* Per-group reservation of serial blocks.
* OWL widget showing prefix utilisation across the chart.
