# Curated OCR demo set (MIRAGE subset)

8 images copied unchanged from `data/ocr_test/mirage/images/` (same dataset, same licence status: **no licence declared,
do not commit or republish**; `images/` and `results/` are git-ignored). Selected by eye on 2026-10-08 from the 40
downloaded images as the most legible handwritten prescriptions that contain an antibiotic order.

| Image | Antibiotic as written (my reading) | Why chosen |
|---|---|---|
| 62qlxpSw | Inj Cefepime 1 g I.V. BD | Generic name, clear print-style hand |
| 4J7Jyojz | Tobramycin eye drops 2 drops each eye TDS x 5 days | Clear, full directions |
| 8aTCyXjA | Tb Oflox-TZ 1-0-1 x 3 days | Clear block capitals |
| 7en1FhHP | Tab Mahacef OZ 1 BD | Neat list layout |
| D8MLkpsp | Syp Augmentin DDS (400 mg/5 ml) 3.5 ml twice daily x 7 days | Clear, full directions; brand is in the catalog |
| D5FMZChe | Tab Azee (500 mg) 1 OD | Numbered list |
| Hy77IZJz | Tab Ciplox (500) 1 BD x 5 days; Ciplox ear drops | Very clear block letters |
| KOsXO4VY | Tab Rifagut 400 mg 1-0-1 x 7 days after meals | Clear, numbered |

Excluded: cursive images (8E7HL1bW, CKYFueDu), the mainly printed e-prescription (2nPPipXy), images with no antibiotic.

Run: `python scripts/ocr_real_eval.py data/ocr_test/demo/images --out data/ocr_test/demo/results`

## Result (pipeline at `e8caeb8`, GLM-OCR revision `2e85a62`, 45 s for 8 images)

Per antibiotic order, checked by hand against the image ("–" = not applicable / not written):

| Image | OCR text of the antibiotic | Name read | Order created | Identified | Dose | Freq | Route | Duration |
|---|---|---|---|---|---|---|---|---|
| 62qlxpSw | `Cefepime 1g` (I.V., BD pushed to other lines) | yes | yes | **cefepime** | 1000 ✓ | missed | missed | – |
| 4J7Jyojz | `To brachyin eye drops 2° in earhye TDS ≤ 5 days` | no | yes | no (R0) | – | 3 ✓ | – ✓ | 5 ✓ |
| 8aTCyXjA | `Follow up: a) TB OFLDX-T2 1-D-1` | partly | **no** (merged with form label, dropped) | – | – | – | – | – |
| 7en1FhHP | `Qb. Malacef. 0z IBD C°` | no | yes | no (R0) | – | missed | missed | – |
| D8MLkpsp | *(line absent from transcript)* | **no** | **no** | – | – | – | – | – |
| D5FMZChe | `Job Azee (5 group)` / `(101)` | yes | yes | no (brand not in catalog) | missed | missed | missed | – |
| Hy77IZJz | `Tab. Ciplox (500) 10m²` | yes | yes | no (brand not in catalog) | missed (no unit) | missed | PO ✓ | missed |
| Hy77IZJz | `Ciplox eld` | yes | yes | no (brand not in catalog) | – | – | – | – |
| KOsXO4VY | `Yab Rifagut 400 mg` / `x 7day` on next line | yes | yes | no (brand not in catalog) | 400 ✓ | missed | missed | missed |

Every image: `evaluate_episode()` ran (status FLAGGED). Every unidentified order received only R0 CANNOT_ASSESS. The
identified cefepime order got R0 PASS, R2 PASS (Watch; no syndrome to compare), and CANNOT_ASSESS for R1, R3, R4
(route and creatinine unknown), R5, R6. No drug was accepted as the wrong drug.

Totals (9 antibiotic orders): name read 5/9; order created 7/9; identified 1/9; dose 2/4 written; frequency 1/6;
route 1/5 applicable; duration 1/3 written. The 8 images produced 79 orders for about 37 real drug lines.

Other OCR errors seen on these clear images: "4 ml thrice daily" (Ventolin) transcribed as "twice daily" — a silent
wrong frequency; "Tab" as "Job"/"Yab"/"Qb"; "1 BD" as "10m²"/"IBD"; "500 mg" as "5 group".
