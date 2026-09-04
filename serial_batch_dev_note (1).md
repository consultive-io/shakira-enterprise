# Dev Note — Phase 2: Unique Serial Numbers & Batch Grouping
**Odoo 19.0 — CE/EE** | Module (suggested): `consultive_serial_batch_basic`
**Depends on:** Phase 1 item-code module (`default_code` generation), `stock`, `mrp`

---

## 1. Scope

Generate a 13-character unique serial number per physical unit, formed as:

```
[7-char default_code from Phase 1][6-digit zero-padded counter]

e.g.  ABCD001  +  000001  =  ABCD001000001
```

Counter is **per product** and starts at `000001`. Uniqueness across products is guaranteed by the 7-char prefix, which Phase 1 already enforces as unique.

Serials are grouped under a **batch** (one per receipt or manufacturing run) which carries the date and warranty basis.

---

## 2. Critical: use Odoo 19's native per-product sequence — do not write a custom generator

Odoo 19 has per-product serial sequencing built in. Verified in `19.0` source:

**`product.template`** (`addons/stock/models/product.py`):
- `lot_sequence_id` — M2o to `ir.sequence`; the sequence used for this product's serials
- `serial_prefix_format` — Char with compute/inverse; **writing to it auto-creates an `ir.sequence`** with that prefix, or reuses an existing sequence whose prefix matches
- `next_serial` — computed preview of the next value

**Both consumption paths honour it:**
- `mrp.production` (`addons/mrp/models/mrp_production.py`, ~line 1583): uses `self.product_id.lot_sequence_id.next_by_id()` when a sequence is set; falls back to `stock.lot._get_next_serial()` only when it isn't
- Receipts: the Generate Serial Numbers flow calls `stock.lot.generate_lot_names(first_lot, count)`, then explicitly advances `product.lot_sequence_id` by the batch size (see the `if product.lot_sequence_id and first_lot:` block in `stock_move.py`, ~line 1197)
- `stock.lot._compute_name` also defaults from `lot_sequence_id.next_by_id()`

**Therefore our job is only to populate `serial_prefix_format` and fix the padding.** Do not override `generate_lot_names`, do not write a custom serial engine. Keeping the native path intact preserves barcode app support, the receipt/MO wizards, and traceability reports.

### Override 1 (confirmed): padding 7 → 6

`_inverse_serial_prefix_format` hardcodes `'padding': 7` when it creates the sequence. We need **6**.

Override `_inverse_serial_prefix_format` on `product.template`: call `super()`, then force `padding = 6` (and `number_increment = 1`, `company_id = False`) on the resulting `lot_sequence_id`. Guard the write so it only touches sequences this module created — check `code == 'stock.lot.serial'` and that the prefix matches the product's `default_code`, so we never mutate a sequence a user configured by hand.

### Override 2 (UNVERIFIED — test before building): receipt wizard prefill

**This is the first task. Do not start coding until it is resolved.**

`product.template._compute_next_serial` formats the value as:

```python
template.next_serial = '{:0{}d}{}'.format(
    template.lot_sequence_id.number_next_actual,
    template.lot_sequence_id.padding,
    template.lot_sequence_id.suffix or ""
)
```

**The prefix is not included** — only number, padding, suffix. Meanwhile `stock.move.next_serial` (the "First SN/Lot" field the Generate Serial Numbers dialog writes into) is a plain `Char` with no compute or default, and `_generate_serial_numbers` builds the entire batch from that string via `generate_lot_names(next_serial, count)`.

If the OWL dialog prefills from `next_serial`, it hands `generate_lot_names` a bare `000001` and the resulting serials carry **no product prefix at all**.

**Test:** set `serial_prefix_format = 'TESTAB1'` manually on one product, save, open a receipt for it, click Generate Serial Numbers.
- Dialog shows `TESTAB1000001` → native path is fine, no override needed
- Dialog shows bare `000001` → override required: seed `stock.move.next_serial` from `lot_sequence_id` with prefix applied (i.e. via `get_next_char`/`next_by_id` semantics) rather than from the prefixless `next_serial`

**Not affected either way:** `mrp.production` uses `lot_sequence_id.next_by_id()`, and `stock.lot._compute_name` does the same. `next_by_id()` applies prefix, padding and suffix correctly. The gap, if real, is confined to the receipt wizard.

---

## 3. New Model: `consultive.stock.batch`

Odoo's `stock.lot` has **no `parent_id`/`child_ids`** — confirmed against 19.0 source. There is no native lot-containing-serials hierarchy, and `product.tracking` is a single selection. The batch layer must therefore be a separate model.

| Field | Type | Notes |
|---|---|---|
| `name` | Char, required, readonly | From `ir.sequence`, e.g. `BATCH/2026/00042` — human-readable, deliberately separate from the item-coding scheme |
| `product_id` | M2o `product.product`, required | |
| `date` | Date, required | Receipt date or MO completion date |
| `source_type` | Selection | `receipt` / `manufacturing` |
| `picking_id` | M2o `stock.picking` | Set for receipts |
| `production_id` | M2o `mrp.production` | Set for MOs |
| `partner_id` | M2o `res.partner` | Supplier, receipts only |
| `warranty_months` | Integer | Default from product (see §5) |
| `warranty_end_date` | Date, computed, stored | `date` + `warranty_months` |
| `lot_ids` | O2m `stock.lot` (`batch_id`) | The serials in this batch |
| `lot_count` | Integer, computed | |
| `company_id` | M2o `res.company`, required | |

Sequence: one `ir.sequence` with `code = 'consultive.stock.batch'`, prefix `BATCH/%(range_year)s/`, padding 5, yearly range.

**Constraint:** all `lot_ids` must share the batch's `product_id`. Enforce in `_check_lot_product`.

---

## 4. Changes to Existing Models

### `stock.lot`
- `batch_id` — M2o `consultive.stock.batch`, `ondelete='restrict'`, `index=True`
- `warranty_end_date` — related `batch_id.warranty_end_date`, stored (stored so it's searchable/filterable in list views and warranty reports)

`ondelete='restrict'` is deliberate: deleting a batch that still has serials attached would orphan warranty data on units that are physically in customers' hands.

### `product.template`
- Set `tracking = 'serial'` on products that carry a generated item code. **Do not force this blindly on every product** — make it the default for coded products but leave the field editable, since services and consumables must stay `none`.
- Auto-populate `serial_prefix_format` (see §5)
- `default_warranty_months` — Integer, default 0; copied onto each batch at creation so historical batches keep their warranty terms even if the product's policy later changes

---

## 5. Prefix Assignment (Gate 3 — at creation, atomic)

In the same `create()` override that Phase 1 uses to generate `default_code`:

1. Generate `default_code` (Phase 1 logic)
2. Immediately write `serial_prefix_format = default_code`
3. Our overridden inverse creates the `ir.sequence` with `padding = 6`

One atomic operation. No lazy path, no chance the sequence is missing at the moment a receipt or MO needs it.

**Backfill:** provide a one-off migration/action that walks existing coded products with an empty `serial_prefix_format` and populates it. Needed for any products created between Phase 1 and Phase 2 deployment.

---

## 6. Batch Creation Hooks

### Receipts — `stock.picking`
Extend `button_validate()`. **After** `super()` (lots must already exist):
- For each incoming picking (`picking_type_id.code == 'incoming'`), group validated move lines by `product_id`
- For each product with tracked lots and no batch yet: create one `consultive.stock.batch` with `date = date_done`, `source_type = 'receipt'`, `picking_id`, `partner_id`, `warranty_months` from the product
- Write `batch_id` on the lots

Handle backorders: a backorder is a separate picking and must produce its **own** batch — the physical goods arrived on a different date, so warranty differs. Do not merge into the original batch.

### Manufacturing — `mrp.production`
Extend `button_mark_done()`, after `super()`:
- Create one batch with `date = date_finished`, `source_type = 'manufacturing'`, `production_id`
- Attach the finished-good lots

MOs producing in multiple steps or with partial completion each get their own batch, same reasoning as backorders.

**Idempotency:** both hooks must be safe to re-enter. Filter to lots where `batch_id` is not set; never create a second batch for the same picking/MO + product pair. Add a unique constraint or an explicit search guard.

---

## 7. Regeneration Guard (Gate 5)

Phase 1's "Regenerate Code" action changes `default_code`. If serials already exist, the issued 13-char serials keep the old prefix while the product moves to a new one — silent, permanent data drift on units already shipped.

**Block it.** In the regenerate method, raise `UserError` if `self.env['stock.lot'].search_count([('product_id', 'in', self.product_variant_ids.ids)])` is non-zero. Enforce at method level, not just by hiding the button.

If a code genuinely must change after serials exist, that's a manual data-migration exercise, not a button.

---

## 8. Validations

- `serial_prefix_format` must equal `default_code` for coded products — add a constraint so manual edits can't desync the two
- Reject `tracking = 'serial'` on a product with no `default_code` (no prefix to build on)
- Batch `date` cannot be in the future
- `warranty_months >= 0`
- Batch `lot_ids` all share `product_id` (§3)

### Duplicate serials — already native, but read the caveats

Do **not** write a duplicate-serial constraint. `stock.lot` already has one:

```python
@api.constrains('name', 'product_id', 'company_id')
def _check_unique_lot(self):
```

It raises a `ValidationError` naming the offending product and serial. Two caveats before relying on it:

1. **Python-level, not SQL.** `@api.constrains` runs through the ORM, so direct SQL writes and some bulk-import paths bypass it. For real hardening add a DB unique index on `(product_id, name, company_id)` — but `company_id` is nullable on `stock.lot`, so a plain unique index misses the null-vs-set case. Use a partial index or a `COALESCE`-based expression index.
2. **Not enforced across companies.** Reading the implementation: it checks company-specific lots against no-company lots, but explicitly *not* between two different companies (the source comment says so). For multi-company clients the same serial can legitimately exist for the same product in company A and company B. Since our 13-char codes are meant to be globally unique physical identifiers, add a stricter cross-company constraint wherever multi-company is in scope.

**Important framing:** this constraint is a *backstop*, not a prevention mechanism. It fires at write time, meaning counter/lot drift (§9) surfaces as an error on a warehouse user's screen mid-receipt, with a message they cannot act on. The duplicate is correctly blocked, but the receipt is stuck until an admin resets the counter. §9 exists so this constraint is never the discovery mechanism.

**Load-bearing dependency:** `_inverse_serial_prefix_format` deduplicates sequences by prefix string — it reuses an existing sequence when the prefix matches. If two products ever share a `default_code`, they silently share one serial counter, and the resulting duplicate serials are very hard to trace after the fact. Phase 1 must have an **SQL unique constraint** on `default_code`, not only Python validation. Verify this before deploying Phase 2.

---

## 9. Serial Verification & Drift Detection

Two different sources of truth exist, and they diverge:

- **The counter** — `lot_sequence_id.number_next_actual` — authoritative for *what generates next*
- **The lots** — `stock.lot` records — ground truth for *what was actually issued*

They drift whenever lots are created by import, manual entry, or a third-party module (the sequence never learns about them), and whenever lots are deleted (the counter never rolls back). Odoo's own `stock.lot._get_next_serial()` sidesteps the counter entirely — it reads the last lot by `id DESC` and increments its name — so it returns a different answer from the counter whenever drift exists.

Build three things:

**1. `last_serial_used`** — computed, non-stored, on `product.template`. Reads the most recent `stock.lot` for the product. This is what a user actually wants to see; expose it on the Inventory tab next to `next_serial`.

**2. Smart button** on the product form → filtered `stock.lot` list for that product, ordered by `name`. Gives immediate visual confirmation of the full issued range.

**3. Drift check** comparing `number_next_actual` against the highest issued serial:
- Surfaced as a warning banner on the product form when the two disagree
- Available as a scheduled `ir.cron` sweeping the whole catalogue, with a summary report of mismatched products
- Include an admin action to resync the counter to `max(issued) + 1`

The cron is the point of this section. Without it, drift is discovered by `_check_unique_lot` (§8) firing at a warehouse user mid-receipt. With it, drift is an admin ticket found overnight.

> `ir.cron` in 19.0 has no `numbercall` / `doall` fields (removed in 17.0) — do not copy older cron definitions.

---

## 10. Views

- **Batch:** list (name, product, date, source, lot count, warranty end) + form with an embedded lot list and a smart button to the serials. Menu under Inventory > Products (or Operations, per house layout).
- **`stock.lot` form/list:** add `batch_id`, `warranty_end_date`. Add a search filter for warranty expiry.
- **Product form, Inventory tab:** show `serial_prefix_format` readonly (it's derived — editing it breaks the §8 constraint), plus `next_serial` and `default_warranty_months`.
- **Picking / MO form:** smart button to related batches.

---

## 11. Security

- `ir.model.access.csv` for `consultive.stock.batch` — read for Inventory User, write/create for Inventory Manager
- Batch `name` and `product_id` readonly after creation
- Batch deletion restricted to Inventory Manager, and blocked entirely when `lot_ids` is non-empty (§4)
- Record rule on `company_id` for multi-company

---

## 12. Documented Limits (Gate 1a — no separator)

Record these in the README; they are accepted consequences of the 13-character no-separator format:

1. **Digit-run merge.** `generate_lot_names` regex-matches the *last* run of digits. `ABCD001` + `000001` reads as the single 9-digit run `001000001`. It increments correctly in normal operation, but at unit **999,999** of one product it rolls over into the Phase 1 item-sequence segment (`001999999` → `002000000`), silently corrupting product identity. Add a monitoring check or a warning at 900,000.
2. **Numeric-only codes.** If the PC/SC segments are numeric, the whole 13 chars are digits with no visible field boundary. Human parsing and any downstream regex become unreliable.
3. **Spreadsheet export.** 13-digit numeric strings become scientific notation in Excel/CSV. Force text formatting in any XLSX export (`xlsxwriter` — set the column format explicitly); brief whoever handles data exports.

---

## 13. Testing Checklist

- **Receipt wizard prefill (§2, Override 2) — run this first**: Generate Serial Numbers on a prefixed product produces `<code>000001`, not a bare `000001`
- Prefix + padding: new coded product gets a sequence with `padding = 6`, prefix `= default_code`; first serial is `<code>000001`
- Manual/pre-existing sequences on a product are not mutated by our padding override
- Receipt of 10 units → 10 serials `000001`–`000010`, one batch, all linked
- MO of 10 units → same, `source_type = 'manufacturing'`
- Second receipt of the same product continues at `000011` (does not reset)
- Two different products both start at `000001` and do not collide
- Backorder produces its own batch with its own date
- Re-validating / re-entering a hook does not create duplicate batches
- Regenerate Code raises `UserError` once any lot exists
- Batch deletion blocked while lots attached
- Backfill action populates `serial_prefix_format` on pre-existing coded products
- `warranty_end_date` computes correctly and survives a later change to the product's `default_warranty_months`
- Concurrency: two simultaneous receipts of the same product produce no duplicate serials

**Verification & drift (§9):**
- `last_serial_used` reflects the most recently issued lot, not the counter
- Deleting a lot leaves the counter unchanged and the drift check flags it
- Importing lots ahead of the counter is detected by the cron, not by a failed receipt
- Resync action sets `number_next_actual` to `max(issued) + 1` and clears the warning
- Duplicate serial entry raises the native `ValidationError` (confirm message names product + serial)
- Multi-company: confirm whether cross-company duplicates are acceptable for this client; if not, the stricter constraint blocks them
