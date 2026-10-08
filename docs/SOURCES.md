# Sources

| Source | Used for |
|---|---|
| [NCDC National Treatment Guidelines for Antimicrobial Use, v2.0 (July 2025)](https://ncdc.mohfw.gov.in/wp-content/uploads/2025/08/NTG-Version-31st-July-final.pdf) | Rule pack: drug choice, dose, duration per syndrome |
| [ICMR Treatment Guidelines for Antimicrobial Use in Common Syndromes (2019)](https://www.icmr.gov.in/icmrobject/custom_data/pdf/resource-guidelines/Treatment_Guidelines_2019_Final.pdf) | Rule pack cross-check |
| [ICMR AMRSN Annual Report 2024](https://www.icmr.gov.in/icmrobject/uploads/Report/1763981012_icmramrsnannualreport2024.pdf) | Coverage priors. Table 2.14: susceptibility counts for urine Enterobacterales (pp. ~75–77) |
| [WHO AWaRe classification 2025](https://www.who.int/publications/i/item/B09489) | AWaRe tiers (verify `data/aware.csv`) |
| [WHONET AMRIE](https://github.com/AClark-WHONET/AMRIE) | `data/reference/amrie/` (non-commercial license) |
| US FDA drug labels via [openFDA](https://open.fda.gov/apis/drug/label/) / DailyMed | `data/renal_dosing.csv`: renal dose bands, quoted per row |
| Cockcroft & Gault 1976, Nephron 16:31-41 | Creatinine clearance estimate in `renal.py` |
| Bielicki et al. 2016, J Antimicrob Chemother, [doi:10.1093/jac/dkv397](https://doi.org/10.1093/jac/dkv397) | WISCA coverage method |
| [AMR R package, `antibiogram.R`](https://github.com/msberends/AMR) | WISCA priors reference (GPL-2: method only, do not copy code) |
| RxHandBD v3 (Mendeley Data) | OCR benchmark dataset (not redistributed) |
