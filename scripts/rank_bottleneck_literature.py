#!/usr/bin/env python3
"""Re-rank the bottleneck bank by topical specificity, not by citation count.

Sorting a keyword-matched bank by citations resurfaces whatever mega-paper
happened to brush the query: the first pass put LAMMPS (molecular dynamics) and
IntCal20 (radiocarbon calibration) at the top of "base rate". This project's
own log records the same failure once before, when an OpenAlex pass sorted by
cited_by_count and returned Nature and Lancet papers instead of the economics
it was after.

So each record is scored against vocabulary specific to its bottleneck, with a
required core term, and citations only break ties.
"""
from __future__ import annotations
import csv, re, sys, math, pathlib
csv.field_size_limit(sys.maxsize)

ROOT = pathlib.Path(__file__).resolve().parents[1]
BANK = ROOT / "data/literature-bank-bottlenecks"
OUT = ROOT / "reports/literature_bottlenecks_ranked.md"

# CORE: at least one must appear, or the record is off-topic for this theme.
# BONUS: each adds weight.
THEMES = {
 "1_base_rate": dict(
   core=[r"class imbalance", r"imbalanc", r"rare (event|class|object)", r"base rate",
         r"cascade", r"coarse[- ]to[- ]fine", r"predictive model", r"region proposal",
         r"hard negative", r"false positive reduction"],
   bonus=[r"detect", r"remote sensing", r"aerial", r"archaeolog", r"screening",
          r"precision", r"large[- ]scale", r"search space", r"prior"]),
 "2_measurement": dict(
   core=[r"confidence interval", r"statistical power", r"sample size", r"bootstrap",
         r"small (sample|test set|n)", r"uncertainty (of|in) (the )?(estimate|metric)",
         r"evaluation (protocol|methodolog)", r"model selection"],
   bonus=[r"precision", r"recall", r"benchmark", r"significance", r"variance",
          r"cross[- ]validation", r"reliab"]),
 "3_prior_shift": dict(
   core=[r"prior shift", r"label shift", r"class prior", r"calibrat", r"dataset shift",
         r"covariate shift", r"positive[- ]unlabel", r"domain (shift|adaptation)",
         r"prevalence"],
   bonus=[r"imbalanc", r"probabilit", r"deploy", r"post[- ]hoc", r"reliability diagram",
          r"temperature scaling", r"threshold"]),
 "4_review_budget": dict(
   core=[r"active learning", r"annotation (budget|cost|effort)", r"query strateg",
         r"human[- ]in[- ]the[- ]loop", r"uncertainty sampling", r"labelling (budget|cost)",
         r"expert (review|verification|validation)", r"crowdsourc"],
   bonus=[r"detect", r"remote sensing", r"archaeolog", r"efficien", r"select",
          r"cost", r"triage"]),
 "5_spatial_validation": dict(
   core=[r"spatial cross[- ]validation", r"block(ed|ing)? cross[- ]validation",
         r"spatial (autocorrelation|dependence)", r"spatial validation",
         r"leave[- ]one[- ]out.*spatial", r"nested cross[- ]validation"],
   bonus=[r"overfit", r"optimistic", r"bias", r"species distribution", r"geospatial",
          r"transferab", r"extrapolat"]),
 "6_spatial_leakage": dict(
   core=[r"leakage", r"group (split|k[- ]?fold)", r"buffered", r"spatial (autocorrelation|dependence)",
         r"inflated (accuracy|performance)", r"overlapping (samples|tiles|patches)"],
   bonus=[r"evaluation", r"bias", r"independen", r"geospatial", r"cross[- ]validation"]),
 "7_weak_supervision": dict(
   core=[r"weakly[- ]supervised", r"weak supervision", r"point[- ]supervis",
         r"box[- ]supervis", r"pseudo[- ]?label", r"pseudo[- ]?mask", r"scribble",
         r"image[- ]level label"],
   bonus=[r"segmentation", r"instance", r"semantic", r"aerial", r"remote sensing",
          r"self[- ]training", r"delineat"]),
 "8_label_noise": dict(
   core=[r"label noise", r"noisy label", r"mislabel", r"confident learning",
         r"annotation error", r"incomplete (inventory|sampling)", r"presence[- ]only",
         r"false (negative|positive) label"],
   bonus=[r"robust", r"clean", r"detect", r"training set", r"bias", r"correct"]),
 "9_data_efficiency": dict(
   core=[r"few[- ]shot", r"low[- ]shot", r"self[- ]supervised", r"limited (labels|annotations|data)",
         r"data[- ]efficient", r"transfer learning", r"fine[- ]tun", r"foundation model",
         r"pre[- ]?train"],
   bonus=[r"remote sensing", r"segmentation", r"detect", r"aerial", r"earth observation",
          r"augmentation", r"scarce"]),
}

def score(rec, spec):
    blob = f"{rec.get('title','')} {rec.get('abstract','')}".lower()
    title = (rec.get("title") or "").lower()
    core_hits = sum(1 for p in spec["core"] if re.search(p, blob))
    if not core_hits:
        return None
    core_title = sum(1 for p in spec["core"] if re.search(p, title))
    bonus = sum(1 for p in spec["bonus"] if re.search(p, blob))
    cit = int(rec.get("cited_by") or 0)
    # La cita solo desempata, y en log para que no domine.
    return core_hits * 3 + core_title * 4 + bonus + math.log10(cit + 1)

def main():
    lines = ["# Literatura por cuello de botella, ordenada por especificidad", "",
             "Puntuada contra vocabulario propio de cada cuello, exigiendo al menos un",
             "termino nuclear. Las citas solo desempatan, en escala logaritmica, para que",
             "un mega-paper que roza la consulta no encabece la lista.", ""]
    for th, spec in THEMES.items():
        f = BANK / f"literature_{th}.tsv"
        if not f.exists():
            continue
        rows = [r for r in csv.DictReader(open(f, encoding="utf-8"), delimiter="\t")
                if len((r.get("abstract") or "").strip()) >= 150]
        scored = []
        for r in rows:
            s = score(r, spec)
            if s is not None:
                scored.append((s, r))
        scored.sort(key=lambda x: -x[0])
        print(f"{th}: {len(rows)} con abstract -> {len(scored)} en tema")
        lines += ["", f"## {th}", "",
                  f"`{len(scored)}` de `{len(rows)}` registros con abstract superan el filtro nuclear.", "",
                  "| pts | cit | año | título | revista |", "|---:|---:|---:|---|---|"]
        for s, r in scored[:15]:
            ti = (r.get("title") or "")[:82].replace("|", "/")
            lines.append(f"| {s:.1f} | {r.get('cited_by')} | {r.get('year')} | {ti} | "
                         f"{(r.get('venue') or '')[:30]} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("informe:", OUT)

if __name__ == "__main__":
    main()
