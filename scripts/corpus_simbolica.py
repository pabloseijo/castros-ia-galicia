#!/usr/bin/env python3
"""Corpus de los dos arqueologos que SI leen la cosmovision castrexa.

Pablo sostiene que la academia gallega ignora la religion y el marco mental de
los castros. La ficha [[historiografia-relixion-castrexa]] ya mostro que no, con
fuentes de la propia USC. Aqui se reune la obra de los dos autores que mejor lo
desmienten, para citarlos por lo que escribieron y no por su resumen:

  Marco V. Garcia Quintela   catedratico USC, religion celta comparada
  Javier Rodriguez-Corral    GEPN-AAT USC, agencia, performatividad, imagenes

## La regla de desambiguacion

[[desambiguar-autor-el-nombre-no-identifica]] costo un corpus de 266 trabajos
para un autor que tiene 50: habia ocho personas con ese nombre. Asi que ORCID
manda —las obras autoafirmadas las reclamo el propio autor— y Crossref solo
completa, con lista negra disciplinar.

Y esta misma sesion dio otro homonimo: `Gonzalo Rodriguez Garcia` es ensayista
de Almuzara, NO arqueologo, y nada tiene que ver con `Javier Rodriguez-Corral`.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

requests.packages.urllib3.disable_warnings()

BASE = Path.home() / "castros" / "papers" / "simbolica"
BASE.mkdir(parents=True, exist_ok=True)
EMAIL = "kelterastudio@gmail.com"
H = {"User-Agent": "MimirCorpus/1.0 (mailto:%s)" % EMAIL, "Accept": "application/json"}

AUTORES = [
    ("garcia-quintela", "Marco V. Garcia Quintela",
     ["Garcia Quintela", "García Quintela"]),
    ("rodriguez-corral", "Javier Rodriguez-Corral",
     ["Rodriguez-Corral", "Rodríguez-Corral", "Rodríguez Corral"]),
]

NEGRA = re.compile(
    r"\b(patient|clinical|carcinoma|tumou?r|nursing|dental|surgery|diabet|"
    r"mercantil|tributari|societari|enfermer|odontolog|didactic|"
    r"nanoparticle|catalysis|polymer|graphene|photovoltaic|"
    r"soccer|futbol|athlete|obesity)\b", re.I)

BUENA = re.compile(
    r"\b(celt|castro|castre|hillfort|iron age|edad del hierro|gallaecia|galicia|"
    r"iberia|prehistor|arqueolog|archaeolog|roman|myth|mito|religio|relixi|"
    r"ritual|sanctuar|santuar|cosmolog|astronom|skyscape|landscape|paisaj|paisax|"
    r"stelae|statue|estatua|guerrer|warrior|druid|sauna|petroglif|rock art|"
    r"antiquity|hagiograph|hagiograf|saint|indo-european|indoeurope|"
    r"comparative|greek|griego|atenas|athens|sacrific|deity|god)\b", re.I)


def get(url, **kw):
    for intento in range(3):
        try:
            r = requests.get(url, headers=H, timeout=45, verify=False, **kw)
            if r.status_code == 429:
                time.sleep(4 * (intento + 1))
                continue
            return r
        except Exception:
            time.sleep(2)
    return None


def orcid_de(apellido):
    q = requests.utils.quote('family-name:"%s"' % apellido)
    r = get("https://pub.orcid.org/v3.0/expanded-search/?q=%s&rows=50" % q)
    if not r or r.status_code != 200:
        return []
    try:
        return r.json().get("expanded-result") or []
    except Exception:
        return []


def obras_orcid(oid):
    r = get("https://pub.orcid.org/v3.0/%s/works" % oid)
    if not r or r.status_code != 200:
        return []
    out = []
    try:
        for g in r.json().get("group", []):
            s = (g.get("work-summary") or [{}])[0]
            t = ((s.get("title") or {}).get("title") or {}).get("value", "")
            y = ((s.get("publication-date") or {}).get("year") or {}).get("value", "")
            doi = ""
            for eid in ((s.get("external-ids") or {}).get("external-id") or []):
                if (eid.get("external-id-type") or "").lower() == "doi":
                    doi = (eid.get("external-id-value") or "").lower()
            if t:
                out.append({"titulo": t, "anno": y or "", "doi": doi, "via": "orcid"})
    except Exception:
        pass
    return out


def obras_crossref(variantes):
    out = []
    for v in variantes:
        cur = "*"
        for _ in range(4):
            r = get("https://api.crossref.org/works",
                    params={"query.author": v, "rows": 100, "cursor": cur,
                            "select": "DOI,title,issued,container-title,author,type",
                            "mailto": EMAIL})
            if not r or r.status_code != 200:
                break
            try:
                m = r.json()["message"]
            except Exception:
                break
            items = m.get("items", [])
            if not items:
                break
            for it in items:
                autores = " ".join("%s %s" % (a.get("given", ""), a.get("family", ""))
                                   for a in (it.get("author") or []))
                an = autores.lower().replace("-", " ")
                if not any(x.lower().replace("-", " ") in an for x in variantes):
                    continue
                t = " ".join(it.get("title") or [])
                if not t or NEGRA.search(t):
                    continue
                rev = " ".join(it.get("container-title") or [])
                if not (BUENA.search(t) or BUENA.search(rev)):
                    continue
                y = ""
                try:
                    y = str(it["issued"]["date-parts"][0][0])
                except Exception:
                    pass
                out.append({"titulo": t, "anno": y, "doi": (it.get("DOI") or "").lower(),
                            "revista": rev, "via": "crossref"})
            cur = m.get("next-cursor")
            if not cur:
                break
    return out


def unpaywall(doi):
    if not doi:
        return None
    r = get("https://api.unpaywall.org/v2/%s?email=%s" % (doi, EMAIL))
    if not r or r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


resumen = {}
for slug, nombre, variantes in AUTORES:
    print("\n" + "=" * 70 + "\n" + nombre + "\n" + "=" * 70, flush=True)
    apellido = "Garcia Quintela" if "Quintela" in nombre else "Rodriguez-Corral"
    cands = orcid_de(apellido)
    print("  ORCID: %d candidatos con ese apellido" % len(cands))
    obras = []
    for c in cands[:10]:
        inst = " ".join(c.get("institution-name") or []).lower()
        gn = (c.get("given-names") or "")
        print("    %s  %s %s  [%s]" % (c.get("orcid-id"), gn,
                                       c.get("family-names"), inst[:50]))
        if not any(k in inst for k in ("santiago", "compostela", "usc", "csic",
                                       "incipit", "sevilla", "oxford", "cambridge")):
            continue
        o = obras_orcid(c["orcid-id"])
        print("      -> %d obras autoafirmadas" % len(o))
        obras += o

    cr = obras_crossref(variantes)
    print("  Crossref (filtrado disciplinar): %d" % len(cr))
    obras += cr

    vistos, unicas = set(), []
    for o in obras:
        k = o["doi"] or re.sub(r"\W+", "", o["titulo"].lower())[:70]
        if k in vistos:
            continue
        vistos.add(k)
        unicas.append(o)
    unicas.sort(key=lambda o: o.get("anno") or "0", reverse=True)
    print("  UNICAS: %d" % len(unicas))

    con_doi = [o for o in unicas if o["doi"]]
    print("  comprobando acceso abierto de %d DOI..." % len(con_doi), flush=True)
    abiertos = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(unpaywall, o["doi"]): o for o in con_doi}
        for f in as_completed(fut):
            o = fut[f]
            d = f.result()
            if d and d.get("is_oa"):
                o["oa"] = d.get("oa_status")
                loc = d.get("best_oa_location") or {}
                o["pdf"] = loc.get("url_for_pdf") or loc.get("url") or ""
                abiertos += 1
    print("  ABIERTOS: %d de %d" % (abiertos, len(con_doi)))

    (BASE / (slug + ".json")).write_text(
        json.dumps(unicas, ensure_ascii=False, indent=1), encoding="utf-8")
    resumen[slug] = {"total": len(unicas), "con_doi": len(con_doi), "abiertos": abiertos}

print("\n" + json.dumps(resumen, indent=1))
