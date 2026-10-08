# Sources

| Source | Used for |
|---|---|
| [NCDC National Treatment Guidelines for Antimicrobial Use, v2.0 (November 2025)](https://ncdc.mohfw.gov.in/uploads/pdf/amr17.pdf) | Rule pack: drug choice, dose, duration per syndrome |
| [ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes (2019)](https://www.icmr.gov.in/icmrobject/custom_data/pdf/resource-guidelines/Treatment_Guidelines_2019_Final.pdf) | Rule pack cross-check; Table 14.1 renal dose modification for parenteral antimicrobials (`data/renal_dosing.csv`) |
| [ICMR AMRSN Annual Report 2024](https://www.icmr.gov.in/icmrobject/uploads/Report/1763981012_icmramrsnannualreport2024.pdf) | Coverage priors. Table 2.14: susceptibility counts for urine Enterobacterales (pp. ~75–77) |
| [WHO AWaRe classification 2025](https://iris.who.int/items/4fa2de82-388c-46d9-a6cb-41ffbd10677d) (CC BY-NC-SA 3.0 IGO) | `data/aware.csv` AWaRe tiers (built by `scripts/build_aware.py`) |
| [WHONET AMRIE](https://github.com/AClark-WHONET/AMRIE) | `data/reference/amrie/` (non-commercial license) |
| [GSK India prescribing information](https://india-pharma.gsk.com/en-in/products/prescribing-information-tab/) (Augmentin, Ceftum, Supacef, Fortum) | `data/brands_india.csv`; oral amoxicillin/clavulanate and cefuroxime renal bands |
| US FDA drug labels via [openFDA](https://open.fda.gov/apis/drug/label/) / DailyMed | Fallback renal bands for oral drugs with no Indian source, labelled per row |
| [MHRA Drug Safety Update, Sept 2014: nitrofurantoin and eGFR](https://www.gov.uk/drug-safety-update/nitrofurantoin-now-contraindicated-in-most-patients-with-an-estimated-glomerular-filtration-rate-egfr-of-less-than-45-ml-min-1-73m2) | Nitrofurantoin renal bands, alongside the US label |
| Cockcroft & Gault 1976, Nephron 16:31-41 | Creatinine clearance estimate in `renal.py` |
| Bielicki et al. 2016, J Antimicrob Chemother, [doi:10.1093/jac/dkv397](https://doi.org/10.1093/jac/dkv397) | WISCA coverage method |
| [AMR R package, `antibiogram.R`](https://github.com/msberends/AMR) | WISCA priors reference (GPL-2: method only, do not copy code) |
| RxHandBD v3 (Mendeley Data) | OCR benchmark dataset (not redistributed) |
