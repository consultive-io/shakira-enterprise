# Python function reference

This document describes every runtime Python function in
`consultive_coa_auto_coding_advanced`, plus the helpers and scenarios in its
test file. It reflects the current implementation, including the native Odoo
Account Type selector and the Coding Group fallback for `account.group_id`.

## How the pieces fit together

```text
Odoo account_type selection
        │
        ├─ account_type_selection() reads the live choices
        └─ post_init_hook() creates caac.account.type wrappers
                    │
                    ├─ a two-digit company-specific code, e.g. 01
                    └─ new account group → 01001, 01002, ...
                                          │
                                          └─ basic module → 01002001, 01002002, ...

Account form
    account_type onchange → technical wrapper relation
    coding_group onchange → standard Group preview
    account.group_id compute → code-derived group, otherwise Coding Group fallback
```

The advanced module generates group prefixes. Account-code allocation itself
is implemented by the dependency `consultive_coa_auto_coding_basic`.

## `hooks.py`

### `_caac_sync_account_types(env)`

Creates missing `caac.account.type` records from Odoo's current
`account.account.account_type` selection.

- **Input:** `env`, the Odoo environment supplied to the install hook.
- **Process:** reads selection values through `account_type_selection`, finds
  existing wrapper records, then creates one wrapper for every missing value.
  It assigns sequences in the order returned by `ordered_account_types`.
- **Output:** the number of wrapper records created.
- **Data impact:** creates wrapper records only; it does not assign any
  two-digit codes.
- **Why it exists:** Odoo's account type is a Selection field, so it cannot
  store the code that this module needs. The wrapper model supplies that
  storage without copying a hard-coded list of Odoo types.
- **Safety:** idempotent. Calling it again only adds newly introduced Odoo or
  third-party selection values.

### `_caac_backfill_accounts(env)`

Associates existing accounts with the wrapper corresponding to their current
standard `account_type`.

- **Input:** an Odoo environment.
- **Process:** loads accounts with no `caac_account_type_id`, then, one wrapper
  at a time, writes that wrapper onto accounts whose `account_type` matches.
- **Output:** number of updated accounts.
- **Data impact:** changes only `caac_account_type_id`; it never changes an
  account code, standard account type, report behavior, or journal entry.
- **Why it is safe:** there is one wrapper per standard selection value.

### `post_init_hook(env)`

The manifest's post-install entry point.

- Calls `_caac_sync_account_types` first, so all wrappers exist.
- Calls `_caac_backfill_accounts` second, so existing accounts can be matched.
- Writes the two counts to the Odoo log.

## `models/caac_account_type.py`

### `account_type_selection(env)`

Returns the live selection list for `account.account.account_type`.

- **Input:** Odoo environment.
- **Output:** a list of `(technical_value, translated_label)` pairs, for
  example `('asset_receivable', 'Receivable')`.
- **Implementation detail:** reads the field definition's
  `_description_selection(env)` instead of maintaining a local list.
- **Benefit:** account types contributed by another module are picked up
  automatically.

### `ordered_account_types(env)`

Orders the selection values to mirror Odoo's Account Type widget.

- **Input:** Odoo environment.
- **Output:** technical selection values ordered as Assets, Liabilities,
  Equity, Income, Expense, Off-balance, then any future unrecognised prefix.
- **Used by:** `_caac_sync_account_types` to make the configuration list easy
  to read.

### `CaacAccountType._compute_display_name()`

Sets the wrapper record's visible label.

- **Dependency:** `name`.
- **Result:** `display_name = name`; for example, `Receivable`, not
  `[01] Receivable`.
- **Reason:** the numeric code is a code-generation setting, not part of the
  accounting type's user-facing label. This also supports the native grouped
  selection UI without displaying prefixes.

### `CaacAccountType._compute_group_count()`

Computes how many coded account groups use each wrapper in the active root
company.

- **Dependency:** active company context.
- **Process:** uses `_read_group` on `account.group`, filtered by wrapper ID
  and root company.
- **Output:** assigns the non-stored `group_count` field.
- **Used by:** the Groups smart button on Account Type Coding.

### `CaacAccountType._check_code()`

Validates a configured two-digit type code.

- **Triggered by:** create or write of `code`.
- **Rules:** empty is allowed; a non-empty value must be exactly two decimal
  digits (`00` through `99`) and unique in the active company context.
- **Failure:** raises `ValidationError` with a user-facing explanation.
- **Why company context matters:** `code` is `company_dependent`; the wrapper
  record is global but each root company can use a different scheme.

### `CaacAccountType._caac_code_is_in_use()`

Returns whether this type has any generated groups in the current root company.

- **Input:** one wrapper record (`ensure_one`).
- **Output:** Boolean.
- **Process:** sudo-searches `account.group` by wrapper and root company.
- **Used by:** `write` to prevent changing a code that already issued group
  prefixes.

### `CaacAccountType.write(vals)`

Protects used type codes, then delegates to normal Odoo write behavior.

- **Input:** field-value dictionary.
- **Rule:** if `code` is changed from an existing value and groups already use
  this type, raises `ValidationError`.
- **Reason:** changing `01` to `02` would not rewrite existing `01001` groups
  and their accounts, making the chart inconsistent.

### `CaacAccountType.action_caac_view_groups()`

Returns an Odoo window action showing groups attached to this wrapper.

- **Input:** one wrapper record.
- **Output:** action dictionary for `account.group` list/form views.
- **Filter:** `caac_account_type_id` equals the current wrapper ID.

## `models/caac_serial_mixin.py`

`CaacSerialAllocatorMixin` is an abstract model reused by account-group code.
It centralises serial formatting and advisory locking; it does not create
business records by itself.

### `CaacSerialAllocatorMixin._caac_lock_prefix(company, prefix)`

Takes a PostgreSQL transaction advisory lock for a root-company/prefix pair.

- **Input:** company record and prefix string, such as `01`.
- **Effect:** allocations under the same prefix wait for each other until the
  transaction commits or rolls back. Different prefixes can allocate in
  parallel.
- **Implementation:** `pg_advisory_xact_lock(company_id, hashtext(prefix))`.
- **Important limitation:** Odoo cursors use `REPEATABLE READ`; a transaction
  that waited on this lock can still have an older query snapshot. Therefore
  the lock reduces, but does not completely eliminate, simultaneous allocation
  collisions. This limitation is also documented in `README.md`.

### `CaacSerialAllocatorMixin._caac_next_serial(prefix, width, used_serials, cache=None)`

Calculates the next sequential serial number.

- **Input:** prefix, trailing width, a set of committed serial integers, and an
  optional in-transaction cache of generated complete codes.
- **Process:** merges the database serials with cached codes, chooses one more
  than the highest serial, and rejects values larger than `10 ** width - 1`.
- **Output:** integer serial; it is not zero-padded yet.
- **Failure:** `ValidationError` when all serial values for the width are used.
- **Note:** it allocates after the current maximum. If the largest existing
  code is deleted, that number can be reused; it is not a persistent sequence.

### `CaacSerialAllocatorMixin._caac_format_code(prefix, width, serial)`

Formats a complete code.

- **Input:** `('01', 3, 2)`.
- **Output:** `'01002'`.
- **Effect:** none; it is a pure formatting helper.

## `models/account_group.py`

### `AccountGroup._caac_type_code(account_type, company)`

Reads the selected wrapper's two-digit code in the requested root-company
context.

- **Input:** `caac.account.type` record and company record.
- **Output:** a configured two-character code such as `01`.
- **Failure:** `ValidationError` when the type has no code for that company,
  with configuration guidance.

### `AccountGroup._caac_used_group_serials(prefix, company, exclude_ids=None)`

Finds already-used group serials below a type prefix.

- **Input:** type prefix, company, and optional group IDs to ignore.
- **Process:** flushes pending prefixes, searches same-root-company group
  prefixes beginning with the requested value, keeps only exact five-character
  numeric suffixes, and returns their integer suffixes.
- **Output:** set such as `{1, 2, 5}` for groups `01001`, `01002`, `01005`.
- **`exclude_ids`:** lets recoding ignore the group currently being recoded.

### `AccountGroup._caac_generate_group_prefix(account_type, company, cache=None, exclude_ids=None)`

Allocates the next five-character group prefix.

- Resolves the wrapper's company code through `_caac_type_code`.
- Takes the per-prefix advisory lock.
- Reads used serials through `_caac_used_group_serials`.
- Calls the mixin's `_caac_next_serial` with a width of three.
- Formats the resulting prefix, e.g. `01` + `002` = `01002`.
- **Output:** complete five-character group prefix.

### `AccountGroup._caac_prefix_vals(prefix)`

Builds the three fields that must receive a generated group prefix.

- **Input:** complete prefix, e.g. `01002`.
- **Output:** dictionary assigning the same value to `code_prefix_start`,
  `code_prefix_end`, and `_basic`'s `coding_prefix`.
- **Reason:** core Odoo resolves account groups from the start/end range;
  `_basic` generates account codes from `coding_prefix`.

### `AccountGroup._caac_has_accounts()`

Checks whether accounts already use this group's start prefix.

- **Input:** one account group.
- **Output:** Boolean.
- **Process:** searches all active and archived accounts for codes beginning
  with the group's prefix in its root company.
- **Used by:** `write` before allowing a group to change account type.

### `AccountGroup.create(vals_list)`

Generates group prefixes during creation when a wrapper type is selected.

- **Input:** one or more standard Odoo create dictionaries.
- **Process:** for each dictionary containing `caac_account_type_id`, allocates
  a prefix and merges `_caac_prefix_vals` into that dictionary. A per-company
  cache prevents duplicate prefixes within a batch before database reads see
  them.
- **Untyped groups:** passed through unchanged, supporting existing/manual
  group ranges.
- **Output:** normal Odoo account-group recordset.

### `AccountGroup.write(vals)`

Handles changing a group's wrapper account type.

- **No new type:** delegates unchanged to Odoo.
- **Multiple groups:** processes each individually because every group needs a
  distinct serial.
- **Same type:** delegates unchanged.
- **Different type with accounts below the current prefix:** raises `UserError`.
- **Different type without accounts:** allocates a new prefix under the new
  type and updates all three prefix fields together.

### `AccountGroup._check_caac_group_code()`

Validates a typed group prefix.

- **Triggered by:** changes to type, start prefix, or end prefix.
- **Rule:** a group with `caac_account_type_id` must have a start prefix of
  exactly five characters.
- **Failure:** raises `ValidationError`.

## `models/account_account.py`

### `AccountAccount._onchange_caac_account_type_id()`

Legacy/programmatic wrapper-to-standard-type synchronisation.

- **Triggered by:** changing `caac_account_type_id`.
- **Effect:** copies the wrapper's technical selection value into standard
  `account_type`.
- **UI note:** the normal form now shows the native `account_type` selector,
  not this technical Many2one field. This onchange remains useful for custom
  forms and code that still writes the wrapper.

### `AccountAccount._onchange_account_type()`

Synchronises the hidden wrapper from the native Odoo Account Type selector.

- **Triggered by:** changing standard `account_type` in the form.
- **Effect:** searches the matching wrapper and sets `caac_account_type_id`.
  Clears it when account type is empty.
- **Why it exists:** account-group coding needs the wrapper relation, but users
  should use Odoo's grouped Balance Sheet / Profit & Loss selector.

### `AccountAccount._onchange_caac_coding_group_id()`

Immediately previews the selected Coding Group in standard Odoo's Group field.

- **Triggered by:** changing `coding_group_id`.
- **Condition:** automatic coding mode with a selected coding group.
- **Effect:** assigns the non-stored `group_id` cache value for the form.
- **Important:** this is a preview. Durable computation after reload is handled
  by `_compute_account_group` below.

### `AccountAccount._compute_account_group()`

Extends Odoo's standard computed Group behavior.

- **Dependencies:** current company context, `code`, and `coding_group_id`.
- **First step:** calls core Odoo's method. Core finds the most-specific
  `account.group` range matching the account code.
- **Fallback:** if core finds no group but a Coding Group exists, uses the
  matching root-company coding group (or the selected group if no mirror is
  found).
- **Why:** migrated accounts can retain a legacy code such as `990001` while
  showing their chosen Coding Group `01002 test` as standard Group.
- **Priority:** valid code-prefix resolution always wins; Coding Group is only
  the fallback.
- **Storage:** `group_id` remains Odoo's non-stored computed field.

### `AccountAccount.create(vals_list)`

Supports creation through the technical wrapper without disrupting Odoo imports.

- **Input:** list of account create dictionaries.
- **Effect:** when a dictionary has `caac_account_type_id` but does not supply
  `account_type`, copies the wrapper's standard type into it.
- **Deliberate exception:** if caller explicitly supplies `account_type`, it
  is preserved. This keeps chart-template installation and imports compatible
  with Odoo core behavior.
- **Output:** normal Odoo account recordset. The `_basic` module's parent
  `create` then performs automatic account-code allocation when applicable.

## `tests/test_account_type_coding.py`

### Test setup helpers

| Function | What it prepares or does |
|---|---|
| `setUpClass` | Sets root-company serial width to 3, obtains model handles, and configures Expenses as `06` and Income as `04`. |
| `_new_group` | Creates a root-company account group with a supplied wrapper type, plus optional overrides. |

### Test scenarios

| Test functions | What they verify |
|---|---|
| `test_every_account_type_is_seeded`, `test_seeding_is_idempotent`, `test_seeded_order_follows_the_type_widget` | All live types are seeded once and ordered like Odoo's selector. |
| `test_code_must_be_two_digits`, `test_two_digit_code_is_accepted`, `test_code_is_unique_within_a_company`, `test_same_code_allowed_in_another_company`, `test_code_cannot_change_once_groups_exist` | Type-code validation, company isolation, and immutability after use. |
| `test_wrapper_fills_account_type_on_create`, `test_wrapper_fills_account_type_via_onchange`, `test_native_account_type_onchange_fills_wrapper` | Synchronisation in both directions between wrapper and standard account type. |
| `test_coding_group_onchange_fills_standard_group`, `test_coding_group_onchange_fills_standard_group_on_existing_account` | New and legacy-style accounts show the Coding Group as standard Group. |
| `test_account_type_stays_writable_without_a_wrapper`, `test_explicit_account_type_wins_over_the_wrapper` | Imports/chart templates can still use standard `account_type` directly. |
| `test_first_group_code_starts_at_one`, `test_group_serial_increments`, `test_group_code_lands_on_all_three_prefix_fields`, `test_types_have_independent_group_serials`, `test_batch_group_creation_does_not_collide` | Prefix generation format, counters, placement, isolation, and batch cache behavior. |
| `test_group_without_a_type_is_untouched`, `test_uncoded_type_is_refused_with_a_clear_error`, `test_group_serial_exhaustion_raises` | Manual-group compatibility and expected allocation failures. |
| `test_changing_group_type_recodes_it`, `test_group_type_cannot_change_once_accounts_exist` | Permitted recoding before use and protection once accounts exist. |
| `test_pdf_worked_example` | End-to-end flow: `06` → `06001` → `06001001`. |

## Related files without functions

- `__manifest__.py` declares dependencies, data files, and `post_init_hook`.
- `__init__.py` and `models/__init__.py` import the module components so Odoo
  registers the hook and model extensions.
- XML files define the native Account Type widget, Coding Group domain, account
  type configuration screens, and group field placement.
