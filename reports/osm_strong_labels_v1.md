# Strong labels from OpenStreetMap

## Why this exists

`accepted_positive_polygons=0` has been the project's top blocker since
the beginning. Without geometry there is no detector, only a chip ranker
that says "this 512 m cell looks castro-ish" and cannot locate anything.

OSM contributors have already traced much of Galicia's archaeology.

## Bank

| class | polygons |
|---|---:|
| castro | `423` |
| mound (mámoa/megalith) | `390` |
| **total** | **`813`** |

- matched to an existing catalogue point (within `250 m`): `726`
- confidence filter applied: `medium` and above

## Size, measured at last

The project could never test whether size separates castros from mámoas,
because it had no geometry. Now it can:

| class | p10 radius | median radius | p90 radius |
|---|---:|---:|---:|
| castro | `38 m` | **`57 m`** | `83 m` |
| mound | `7 m` | **`10 m`** | `20 m` |

Castros are about `5.5x` the radius of mounds. That is the physical difference the 5 m ring features were too coarse to exploit.

## What this is not

- **Not ground truth.** OSM geometry is volunteered, traced from imagery,
  and of uneven precision. Some outlines are the enclosure, others the hill.
- **Not verified archaeology.** A `hill_fort` tag is a contributor's opinion.
- **Not a licence shortcut.** OSM is ODbL: derived data carries obligations,
  which matters if any of this is ever published.

It is a review bank that turns a blocked task into a checking task, which
is a far cheaper kind of work than drawing several hundred polygons by hand.

## Next

1. Open the GeoPackage in QGIS and check a sample against PNOA and hillshade.
2. Promote the ones that survive into `data/annotations/`.
3. With geometry on both classes, an object detector becomes possible.

