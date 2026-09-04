# Serial Numbers & Batch Grouping

Gives every physical unit a 13-character serial number, and groups the units that
arrived together into a **batch** that carries their date, supplier and warranty.

```
Internal Reference (7):  ZIZT001
Serial number     (13):  ZIZT001000001
                         └─ 7-char code ─┘└ 6-digit counter ┘
```

The counter runs per product and is drawn from Odoo's own per-product `ir.sequence`,
so the receipt wizard, the barcode app, manufacturing orders and the traceability
reports all keep working as shipped. This module decides only the prefix and the
padding; it does not replace Odoo's serial number engine.

---

## Why batches exist

A serial number is pure identity. `ZIZT001000001` and `ZIZT001000500` might be six
months apart or the same afternoon — the counter says nothing about time. Three
facts about a unit have nowhere else to live:

- **when it arrived**, which is when its warranty starts
- **who supplied it**, which is who a warranty claim goes back to
- **which delivery it came from**, which is what a recall has to target

Odoo has no native home for them. `stock.lot` has no parent/child hierarchy, and
`product.tracking` is a single selection — a product is tracked by lot *or* by
serial, never both — so "these 200 units arrived together" is inexpressible. Hence
a separate model, `inventory.serial.batch`, at a grain of **one document, one
product**: a receipt covering three tracked products produces three batches, and a
backorder produces its own, because the goods physically arrived on a different day.

### A worked example

Two products with very different terms:

| Product | Internal Ref | Warranty |
|---|---|---|
| Induction Flat Top Cooker | `ZIZT001` | 24 months |
| Griddle Plate | `ZIZT002` | 6 months |

**10 March 2026** — 200 cookers land from Guangdong Appliance Co on receipt
`WH/IN/00123`. Validating it creates:

```
BATCH/2026/00001   Cooker   2026-03-10   Guangdong Appliance   24 months
                                         → warranty ends 2028-03-10
   serials ZIZT001000001 … ZIZT001000200
```

**2 September 2026** — 150 griddles from a different supplier, `WH/IN/00287`:

```
BATCH/2026/00042   Griddle  2026-09-02   Foshan Metalworks      6 months
                                         → warranty ends 2027-03-02
   serials ZIZT002000001 … ZIZT002000150
```

What this buys, day to day:

- A customer brings a dead unit to the service counter. Staff read the 13 characters
  off the rating plate — that is all they have — and get arrival date, supplier and
  warranty status from one lookup.
- Guangdong later admits a bad capacitor run in the March shipment. The recall needs
  *those 200 units*: not every cooker ever sold, and not a guessed serial range. The
  batch is the only record of which units came off that container.

### The failure the constraints prevent

A receipt is mis-scanned and a clerk fixes it by hand on the lot form, attaching
griddle serial `ZIZT002000087` to `BATCH/2026/00001` — the **cooker** batch. One
field, one record.

`stock.lot.warranty_end_date` is a *stored* related field reaching through
`batch_id`, so that griddle's own row now holds `2028-03-10`. Its real cover ended
`2027-03-02`.

**November 2027.** The customer returns with a burnt element, 14 months old and eight
months out of warranty. Warranty status reads "covered until March 2028", and a free
replacement is approved. Then it compounds:

- **It cannot be recovered.** Claims go back to the supplier on the batch —
  Guangdong, who never sold a griddle. Foshan's claim window shut in March.
- **It poisons the recall.** The griddle sits inside the cooker defect batch, and is
  missing from every griddle quality analysis.
- **Nothing looks wrong.** The lot form shows a date, the batch shows a date, and
  they agree with each other perfectly. They describe a different appliance.

One unit is a bad afternoon. The path this actually travels is a hook attaching a
whole delivery at once — 150 griddles carrying a cooker's warranty, discovered one
claim at a time over two years, by which point the supplier claim window is closed.

That is what `stock.lot._check_batch_product` is for, and why it lives on the **lot**
rather than only on the batch: serials are attached by writing `batch_id` on the lot,
and an `@api.constrains('lot_ids')` on the batch only fires when the one2many is
written through the batch itself.

---

## How a serial and a batch actually get made

Three sequences are involved, created at different times and living for different
spans. Following one receipt end to end is the quickest way to see which does what.

| | Sequence code | Prefix | Padding | Hands out | Lifetime |
|---|---|---|---|---|---|
| ① | `inventory.item.code.<PC><SC>` | — | 3 | the `001` inside the product code | per leaf product category, forever |
| ② | `stock.lot.serial` | `ZIZT001` | 6 | serial numbers | per product, forever |
| ③ | `inventory.serial.batch` | `BATCH/%(range_year)s/` | 5 | batch names | per year, resets each January |

Sequences ① and ② are created when the product is created. ③ ships with the module.

### Months earlier — creating the product

Phase 1's `_generate_item_code()` assembles the code from the classification and
draws the running number from sequence ①:

```
item_code    = ZF + ZH + ZI + ZT + 001  = ZFZHZIZT001   (11 chars)
default_code =           ZIZT + 001     = ZIZT001       (7 chars — the last 7)
```

This module then writes `serial_prefix_format = 'ZIZT001'`. That triggers core's
inverse, which creates sequence ② with `padding = 7`; `_align_serial_sequence()`
immediately forces it to **6**, because a 7-character prefix plus a 7-digit counter
would be 14 characters and the specification is 13.

### Receipt day — drawing the serial

The operator opens the receipt and clicks **Generate Serial Numbers**. The dialog
does **not** prefill: "First Serial Number" is empty on its placeholder. Clicking
**"New"** beside it calls `ir.sequence.next_by_id()` on the product's sequence ②,
which applies prefix, padding and suffix:

```
'ZIZT001' + '%06d' % 1  →  ZIZT001000001
```

Entering a quantity of 3 expands that through `generate_lot_names`, which increments
the **last run of digits**. Note that `ZIZT001000001` ends in `001000001` — the
product code's trailing digits run straight into the counter — so the run being
incremented is nine digits, not six. It counts correctly, and it is also the reason
for limit 1 below.

Three `stock.move.line` records are written carrying `lot_name` **strings**. At this
point no `stock.lot` records exist, and no batch exists.

### Validation — strings become records, then a batch

`button_validate()` → `_action_done()` turns those strings into real `stock.lot`
records (`_create_and_assign_production_lot`). **Only now** is there anything to
group, which is why the batch hook runs after `super()` rather than before it.

The hook then collects `picking.move_line_ids.lot_id`, groups by product, and creates
the batch. Its name comes from sequence ③, which is date-ranged: a child counter is
created per year, and the year in the prefix is interpolated from that range.

```
'BATCH/' + '2026' + '/' + '%05d' % 1  →  BATCH/2026/00001
```

The batch's own date is passed to the sequence, not today's date, so a batch recording
a December delivery entered in January draws `BATCH/2025/…` from the 2025 counter —
its number and its year agree.

Finally `batch_id` is written onto the lots, which also pushes the stored
`warranty_end_date` onto each one.

```
BATCH/2026/00001   Cooker   2026-03-10   Guangdong   24 months → 2028-03-10
  ├── ZIZT001000001
  ├── ZIZT001000002
  └── ZIZT001000003        each carrying warranty_end_date 2028-03-10
```

### When only part of the delivery arrives

If 2 of 3 cookers arrive, core returns a **backorder wizard** out of
`_pre_action_done_hook` without validating anything — the picking is still not `done`.
The hook runs, sees that, and creates **no batch**, which is correct: nothing has been
received yet.

Confirming the wizard re-enters `button_validate`, and that pass creates the batch for
the 2 units received. The third arrives weeks later on its own backorder picking and
earns its own batch, dated then — so its warranty runs from the day it actually
arrived. This is why the hook re-checks `state == 'done'` instead of assuming it, and
why it must be safe to run twice.

---

## Where to find things

| What | Where |
|---|---|
| All batches | **Inventory → Products → Serial Batches** |
| A unit's batch and warranty | **Lots / Serial Numbers** — `Batch` and `Warranty End` columns, plus *Under Warranty* / *Warranty Expired* filters |
| Batches from one receipt or MO | **Batches** smart button on the receipt or manufacturing order |
| A product's serial state | Product → **Inventory** tab: `Next Serial`, `Last Serial Used`, `Warranty (Months)` |
| Counter recovery | Warning banner on the product form → **Resync Counter** (Inventory Manager) |

Batches are read-only for Inventory Users and editable by Inventory Managers.
Nobody can delete one that still holds serials, and deletion is reserved for
system administrators even when it is empty — a batch is the only record of when
a unit arrived and under what terms.

---

## Accepted limits

These follow from the 13-character no-separator format and are accepted, not bugs.

1. **Digit-run merge at 999,999 units.** `generate_lot_names` increments the *last*
   run of digits, and `ZIZT001` + `000001` reads as the single 9-digit run
   `001000001`. It increments correctly in normal use, but at unit 999,999 of one
   product it rolls over into the item-code segment (`001999999` → `002000000`),
   silently changing product identity. Monitor, and raise a warning at 900,000.
2. **Numeric-only codes have no visible boundary.** If the product category segments
   are numeric, all 13 characters are digits with nothing marking where the code ends
   and the counter begins. Human reading and downstream regex both become unreliable.
3. **Spreadsheets mangle 13-digit strings.** Excel and CSV turn them into scientific
   notation. Force text formatting in any XLSX export (set the column format
   explicitly in `xlsxwriter`) and brief whoever handles data exports.

## Decisions worth knowing

- **Single-variant products only.** A serial prefix and `lot_sequence_id` both live on
  the product, not the variant, so every variant would share one counter and a serial
  could not say which variant a unit is. Multi-variant templates are refused an item
  code. `_item_code_supports_variants()` is the seam if this changes.
- **The Generate Serial Numbers wizard is left native.** It does not prefill the first
  serial — users click **"New"** beside the field, which draws from the product's
  sequence and applies the prefix. Nothing is patched, so drift detection is the
  safety net rather than a locked-down wizard.
- **Zero warranty months means no end date**, not a term expiring the day it began.
  `warranty_end_date` is left empty so an uncovered unit never reads as a covered one
  whose cover has lapsed.
- **Warranty is snapshotted onto the batch**, not read through to the product.
  Changing a product's policy affects future batches only; units already sold keep
  the terms they were sold under.
