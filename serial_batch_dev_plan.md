# Development Plan — Phase 2: `cnslt_serial_batch_basic`

> **Naming (decided):** the batch model is **`inventory.serial.batch`**, matching the
> Phase 1 convention (`inventory.category`, `inventory.type`) rather than the note's
> `consultive.stock.batch` — no company name in a model name. The module is
> **`cnslt_serial_batch_basic`**, matching `cnslt_item_code_generator`, the module it
> extends. Substitute both wherever the dev note says otherwise.

## Context

`serial_batch_dev_note (1).md` specifies Phase 2: a 13-character serial per physical
unit (`[7-char default_code][6-digit counter]`) grouped under batches carrying date and
warranty. It builds on `cnslt_item_code_generator`, which already issues the 7-char
`default_code`.

The note left two items open. Both are now resolved against the 19.0 source at
`/home/abrar/odoo/odoo_19/odoo/addons/`, and one resolves differently than the note
predicted. This plan folds those corrections in.

**Locked decisions (from the user):**
- Multi-variant products are out of scope — single-variant only. Guard and document.
- The native Generate Serial Numbers wizard is left alone: no JS patch, no server-side
  prefix constraint on lot names. This makes §9 drift detection the sole safety net, so
  it is promoted from "nice to have" to required scope.

---

## Findings that change the note

### §2 Override 2 — resolved, and neither branch applies

The wizard does not prefill at all. `generate_serial.js:39-46` (`onMounted`) sets only
`nextSerialCount`/`totalReceived`; "First Serial Number" stays empty on the placeholder
`e.g. LOT-PR-00012`. The **"New" button** beside it (`lots_dialog.xml:33` →
`_onGenerateCustomSerial`, `generate_serial.js:48-56`) calls
`ir.sequence.next_by_id()`, which **does** apply prefix + padding + suffix.

`product.template.next_serial` is never read by the wizard, so the note's feared
prefixless `000001` cannot occur. **No override is needed.** Per the locked decision we
ship nothing here — but note two consequences that Work item 7 must absorb:

1. Clicking "New" then **Discard** burns a sequence number with no lot issued.
   `stock_move.py:1202-1207` exists to compensate, and comments say so.
2. That compensation only fires when the entered value matches
   `get_next_char(first_number)` or `get_next_char(first_number + increment)`. A
   hand-typed serial matches neither, so the counter is not advanced and the next
   receipt re-issues the same number → `_check_unique_lot` fires mid-receipt.

### §8 "load-bearing dependency" — confirmed unmet, and it is a prerequisite

There is **no SQL unique constraint on `default_code`** anywhere: core has only an
`@api.onchange` warning (`product/models/product_template.py:422-434`, UI-only — silent
on `create()`, `load()`/import and RPC), and `cnslt_item_code_generator` adds none.

Since `_inverse_serial_prefix_format` dedupes sequences by prefix string
(`stock/models/product.py:911-916`), two products sharing a `default_code` would
**silently share one serial counter**. This must land before Phase 2 is deployed.

The constraint belongs on **`product.product`** — the column lives there
(`product/models/product_product.py:35`); `product.template.default_code` is
compute/stored and propagates to the variant only for single-variant templates.

### §6 hooks — "after `super()`" is not sufficient

Both entry points return a wizard action **without validating anything**:
- `stock_picking.py:1413-1432` — `res = self._pre_action_done_hook(); if res is not True: return res`
- `mrp_production.py:2219-2222` — `res = self.pre_button_mark_done(); if res is not True: return res`

So the hooks must filter on `state == 'done'` after `super()`, not assume it. When the
user confirms the wizard it re-enters `button_validate`, so the idempotency guard the
note asks for in §6 is doing real work, not just defending against double-clicks.

### §6 MRP field name changed in 19.0

It is `lot_producing_ids` (**Many2many**, `mrp_production.py:120`), not the
`lot_producing_id` M2o of earlier versions. Finished-good lots also reach
`move_finished_ids.move_line_ids.lot_id`. Use `finished_move_line_ids`
(`mrp_production.py:565-568`) as the source, and treat `lot_producing_ids` as a
cross-check.

### Everything else in the note verified as written

`lot_sequence_id`/`serial_prefix_format`/`next_serial` (`product.py:853-859`); `padding: 7`
hardcoded (`product.py:922`); MO uses `next_by_id()` (`mrp_production.py:1583-1593`);
receipt advances the sequence (`stock_move.py:1197-1209`); `stock.lot` has no
`parent_id`/`child_ids`; `_check_unique_lot` is Python-level and explicitly not
cross-company (`stock_lot.py:103-125`, see comment at :117); `_get_next_serial` reads
last lot by `id DESC` (`stock_lot.py:92-101`); `generate_lot_names` matches the **last**
digit run (`stock_lot.py:72-90`), so `INFT001`+`000001` is one 9-digit run — §12.1 holds;
`ir.cron` has no `numbercall`/`doall`.

**Override 1 is smaller than the note assumes:** `_inverse_serial_prefix_format` already
sets `code='stock.lot.serial'` and `company_id=False`, and `number_increment` defaults
to 1. Only `padding` needs forcing.

---

## Work item 0 — Prerequisites in `cnslt_item_code_generator`

Ships first, separately, and is deployable on its own.

**New `models/product_product.py`:**
```python
class ProductProduct(models.Model):
    _inherit = 'product.product'

    _default_code_uniq = models.UniqueIndex(
        "(default_code) WHERE default_code IS NOT NULL AND default_code != ''",
        "The Internal Reference must be unique: two products sharing one would "
        "silently share a serial number counter.",
    )
```
`models.UniqueIndex` is the 19.0 API (`odoo/orm/table_objects.py:185`); it takes a
definition and a message. A partial index is required — a plain `unique(default_code)`
would let two `''` values collide while allowing many NULLs.

~~**New `hooks.py` with a `pre_init_hook`**~~ — **dropped (2026-09-04).** It would only
have improved the error message when installing over duplicate codes, and it fires on
install only (`loading.py:180`), so it would never run on the already-installed
databases. Checked against `shakira`: 7 products carry an Internal Reference and none
collide, so the index applies cleanly. If a future install does hit a duplicate, the
index still refuses it — with a bare Postgres error rather than a named list.

**Single-variant guard** in `_generate_item_code`
([product_template.py:52](cnslt_item_code_generator/models/product_template.py#L52)) —
raise `ValidationError` if `len(self.product_variant_ids) > 1`, naming the reason
(one serial prefix per template; a multi-variant template cannot identify a unit).

**Tighten `security/ir.model.access.csv`** — it currently grants unrestricted CRUD on
`inventory.category`/`inventory.type` to every internal user with no group. Read for
`base.group_user`, write/create/unlink for `stock.group_stock_manager`.

---

## Work item 1 — Module skeleton

```
cnslt_serial_batch_basic/
├── __init__.py  __manifest__.py  README.md
├── data/        ir_sequence_data.xml, ir_cron_data.xml
├── models/      __init__.py, inventory_serial_batch.py, product_template.py,
│                stock_lot.py, stock_picking.py, mrp_production.py
├── security/    ir.model.access.csv, batch_security.xml
├── tests/       __init__.py, test_serial_prefix.py, test_batch.py, test_drift.py
└── views/       inventory_serial_batch_views.xml, product_views.xml,
                 stock_lot_views.xml, stock_picking_views.xml, mrp_production_views.xml
```

`depends = ['cnslt_item_code_generator', 'stock', 'mrp']`, `license = 'LGPL-3'`,
`version = '19.0.1.0.0'`, author `Consultive` — matching the two existing modules.

---

## Work item 2 — Prefix assignment and padding (§2 Override 1, §5)

`models/product_template.py`, `SERIAL_PADDING = 6`:

- **`_generate_item_code()`** — call `super()`, then `self.serial_prefix_format = self.default_code`.
  Reusing Phase 1's existing method keeps §5's "one atomic operation" property; no new
  `create()` override is needed.
- **`_inverse_serial_prefix_format()`** — call `super()`, then force `padding = 6` on
  `lot_sequence_id`, guarded exactly as §2 asks: only when
  `sequence.code == 'stock.lot.serial'` **and** `sequence.prefix == template.default_code`.
  A hand-configured sequence is never mutated.
- **`action_backfill_serial_prefix()`** (§5) — walks coded products with empty
  `serial_prefix_format` and populates it. Exposed as an `ir.actions.server` on the
  product list Action menu, restricted to `stock.group_stock_manager`.
  (Dropped 2026-09-04, reinstated the same day.) Note `serial_prefix_format` is
  computed and **not stored**, so it cannot be searched: the domain keys off
  `lot_sequence_id` being unset or still pointing at `stock.sequence_production_lots`,
  which is core's default for the field.
- **`default_warranty_months`** — Integer, default 0 (§4).
- **`last_serial_used`** — computed, non-stored; most recent `stock.lot` for the
  product (§9.1).
- **`serial_counter_drift`** — computed, non-stored Boolean + a message field, driving
  the form warning banner (§9.3).

Verify by test that the inverse sees the **new** `default_code` — it fires at flush,
after Phase 1's write, but this ordering is worth pinning rather than assuming.

Do **not** blanket-set `tracking = 'serial'` (§4). `tracking` is computed in 19
(`stock/models/product.py:846-852`) and forced to `none` for non-storable products;
make it the default for coded storable goods and leave it editable.

---

## Work item 3 — `inventory.serial.batch`

Fields per note §3 verbatim (table `inventory_serial_batch`). Sequence in
`data/ir_sequence_data.xml`: `code='inventory.serial.batch'`, prefix
`BATCH/%(range_year)s/`, padding 5, `use_date_range=True`, `company_id=False`.

Constraints: `_check_lot_product` (all `lot_ids` share `product_id`), `warranty_months >= 0`,
`date` not in the future. `warranty_end_date` computed stored from `date + warranty_months`.

---

## Work item 4 — `stock.lot` and views on existing models

`stock.lot`: `batch_id` (M2o `inventory.serial.batch`, `ondelete='restrict'`, `index=True`) and
`warranty_end_date` (related, **stored** — searchable for warranty reports).

Batch `unlink()` blocked while `lot_ids` is non-empty (§11).

---

## Work item 5 — Creation hooks (§6)

Shared helper `_create_serial_batches()` so receipts and MOs share one implementation.

**`stock.picking.button_validate()`** — `super()`, then operate only on
`self.filtered(lambda p: p.state == 'done' and p.picking_type_id.code == 'incoming')`.
Group done move lines by `product_id`; for each product with lots lacking a `batch_id`,
create one batch (`date = date_done`, `source_type='receipt'`, `picking_id`, `partner_id`,
`warranty_months` snapshotted from the product) and write `batch_id` on those lots.

**`mrp.production.button_mark_done()`** — `super()`, then
`self.filtered(lambda p: p.state == 'done')`. Source lots from `finished_move_line_ids`
filtered to `product_id == production.product_id`. `date = date_finished`,
`source_type='manufacturing'`, `production_id`.

**Idempotency (§6)** — both filter to lots where `batch_id` is unset, and both search for
an existing batch on the same (picking|production, product) pair before creating. Backorder
pickings and split MOs are separate records in `state='done'` at their own time, so they
naturally get their own batch with their own date; no special handling, but a test each.

---

## Work item 6 — Regeneration guard (§7)

Override `action_regenerate_item_code`
([product_template.py:173](cnslt_item_code_generator/models/product_template.py#L173))
in the **new** module: raise `UserError` when
`self.env['stock.lot'].search_count([('product_id', 'in', self.product_variant_ids.ids)])`
is non-zero. Enforced in the method, not by hiding the button.

Keeping this in Phase 2 rather than Phase 1 means Phase 1 stays independently
deployable and the guard exists exactly when serials do.

---

## Work item 7 — Drift detection (§9) — required scope

With the wizard left native, this is the only thing standing between a mistyped serial
and `_check_unique_lot` firing at a warehouse user mid-receipt.

- **`last_serial_used`** on the product form beside `next_serial` (Work item 2).
- **Smart button** → `stock.lot` filtered to the product, ordered by `name` (§9.2).
- **Drift check** comparing `lot_sequence_id.number_next_actual` against the highest
  issued serial. Surfaced as a form banner; swept nightly by an `ir.cron`
  (`data/ir_cron_data.xml` — no `numbercall`/`doall`, removed in 17.0) producing a
  summary of mismatched products.
- **`action_resync_serial_counter()`** — sets `number_next_actual` to `max(issued) + 1`,
  restricted to `stock.group_stock_manager`, logged to the product chatter.

Parsing the highest issued serial must strip the product's own prefix before comparing
numerically, and must tolerate lots that do not match the prefix at all (hand-typed ones)
— those are themselves a drift signal and should be reported, not crash the sweep.

---

## Work item 8 — Views and security (§10, §11)

Batch list + form (embedded lot list, smart button to serials), menu under Inventory >
Products. `batch_id`/`warranty_end_date` on `stock.lot` form and list plus a warranty-expiry
search filter. Product Inventory tab: `serial_prefix_format` readonly, `next_serial`,
`last_serial_used`, `default_warranty_months`. Smart buttons to batches on picking and MO.

`ir.model.access.csv`: read for `stock.group_stock_user`, write/create for
`stock.group_stock_manager`, unlink manager-only — the model reference is
`model_inventory_serial_batch`. `company_id` record rule in `batch_security.xml`.
`name` and `product_id` readonly after creation.

---

## Work item 9 — README (§12)

Record the three accepted limits: digit-run merge at 999,999 units per product (with the
warning threshold at 900,000), numeric-only codes having no visible field boundary, and
13-digit strings becoming scientific notation in Excel — force text formatting in XLSX
exports. Also record the two decisions locked here: single-variant only, and native
wizard behaviour (users must click "New").

---

## Tests

Note §13's checklist, minus the wizard-prefill item (resolved, nothing to test), plus:

- Padding override applies to a generated product; a hand-configured sequence with a
  different prefix is left untouched
- `_inverse_serial_prefix_format` sees the post-write `default_code` (ordering)
- `button_validate` returning a backorder wizard creates **no** batch; the follow-up
  confirmed call creates exactly one
- `button_mark_done` returning a consumption warning creates no batch
- Re-entering either hook creates no second batch
- Backorder picking and split MO each produce their own batch with their own date
- Two products both start at `000001` and do not collide; a second receipt continues
- Regenerate raises `UserError` once any lot exists
- Batch deletion blocked while lots attached
- `last_serial_used` reflects the last lot, not the counter; deleting a lot leaves the
  counter and the drift check flags it; resync clears it
- Drift sweep tolerates a hand-typed lot that does not match the prefix
- Work item 0: duplicate `default_code` is refused at DB level via `create`, `load()`
  and direct write
- Work item 0: a multi-variant template is refused an item code

---

## Verification

1. `-u cnslt_item_code_generator` on a copy of production first — Work item 0's index
   will fail if duplicates exist. Confirmed clean on `shakira` (7 coded products, no
   collisions) by the grouping query in Work item 0.
2. `odoo-bin -i cnslt_serial_batch_basic --test-enable --test-tags /cnslt_serial_batch_basic`
3. Manual: create a coded product → confirm `ir.sequence` exists with `padding=6` and
   `prefix == default_code`; receive 10 units via a receipt, clicking **"New"** in the
   Generate Serial Numbers dialog → expect `INFT001000001`–`INFT001000010`, one batch,
   all lots linked, `warranty_end_date` populated.
4. Manual drift: delete one lot, reload the product form, confirm the banner appears;
   run the cron manually; use the resync action and confirm the banner clears.
5. Manual backorder: receive 6 of 10, confirm the backorder, validate it later →
   two batches with different dates.
