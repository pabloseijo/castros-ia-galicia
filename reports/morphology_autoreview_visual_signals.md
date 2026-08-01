# Morphology Autoreview Visual Signals

Generated: 2026-08-01

## What This Is

Second-pass visual verifier over the autonomous control set v1 thumbnails.
It measures whether the official orthophoto chip contains centered edge, texture and radial-ring signal around the provisional catalogue-point radius.

This is not an archaeological acceptance label and it does not promote any row into training.
The field `training_use` remains `exclude_until_independent_label_review`.

## Inputs And Outputs

- Input manifest: `data/morphology-autoreview-v1/orthophoto_thumbnail_manifest.tsv`
- Input decisions: `data/morphology-autoreview-v1/autoreview_decisions.tsv`
- Output scores: `data/morphology-autoreview-v1/visual_signal_scores.tsv`
- Output points: `data/morphology-autoreview-v1/control_set_v1_visual_scores.geojson`
- Optional QGIS package: `data/morphology-autoreview-v1/morphology_autoreview_v1_visual_signals.gpkg`

## Counts

- Rows checked: 201
- Valid thumbnails scored: 200
- Failed or unusable thumbnails: 1
- Median score, all valid: 25.84
- Median score, positives: 27.60
- Median score, negatives: 23.89
- P25/P75 score, positives: 18.18 / 40.45
- P25/P75 score, negatives: 15.88 / 35.34

### By Role And Tier

- negative/-: 1
- negative/moderate_centered_ring_signal: 12
- negative/strong_centered_ring_signal: 3
- negative/weak_centered_ring_signal: 85
- positive/moderate_centered_ring_signal: 14
- positive/strong_centered_ring_signal: 7
- positive/weak_centered_ring_signal: 79

### Autonomous Visual Decisions

- negative/hard_negative_visual_signal_moderate_keep_as_distractor: 12
- negative/hard_negative_visual_signal_strong_keep_as_distractor: 3
- negative/negative_control_visual_signal_weak: 85
- negative/thumbnail_unusable_refetch_or_manual_followup: 1
- positive/positive_control_visual_signal_moderate: 14
- positive/positive_control_visual_signal_strong: 7
- positive/positive_control_visual_signal_weak_followup: 79

## Strongest Positive Visual Signals

- control-v1-0052 | Castro de Santa Mariña/Castrosante | score 75.79 | coastal_promontory_hint
- control-v1-0059 | Castro de Santa Mariña | score 69.34 | coastal_promontory_hint
- control-v1-0088 | Castro de Santa Justa | score 68.76 | earthwork_or_wall_hint
- control-v1-0041 | Castro de Entretorres/Castro de Punta Galeana | score 66.98 | coastal_promontory_hint
- control-v1-0065 | A Roda do Castro | score 66.01 | earthwork_or_wall_hint
- control-v1-0039 | Castro de Punta Sardiñeiro | score 65.93 | coastal_promontory_hint
- control-v1-0061 | Castro de Santa María da Frairía | score 62.88 | coastal_promontory_hint
- control-v1-0057 | Castro de Cabo Burela | score 61.91 | coastal_promontory_hint
- control-v1-0030 | Castro de Santa Marta de Babío | score 59.91 | coastal_promontory_hint
- control-v1-0069 | Castro de Castromiñán | score 59.86 | earthwork_or_wall_hint

## Weakest Positive Visual Signals

- control-v1-0046 | Casa reitoral de Santa María de Castrofeito | score 9.95 | coastal_promontory_hint
- control-v1-0066 | Castro de Castelo | score 10.29 | earthwork_or_wall_hint
- control-v1-0002 | Castro da Cividade | score 10.55 | large_castrexo_civitas_hint
- control-v1-0089 | Caracuto do Castro | score 10.90 | earthwork_or_wall_hint
- control-v1-0098 | Castro de São Domingos/ Cristelos | score 12.18 | earthwork_or_wall_hint
- control-v1-0083 | Castro | score 12.33 | earthwork_or_wall_hint
- control-v1-0099 | Arados/Castro de Arados | score 12.44 | earthwork_or_wall_hint
- control-v1-0087 | Castro de Escariz / São Ilus | score 12.78 | earthwork_or_wall_hint
- control-v1-0085 | Castro de Atafona | score 13.60 | earthwork_or_wall_hint
- control-v1-0011 | Cividade | score 14.26 | large_castrexo_civitas_hint

## Strongest Hard-Negative Visual Distractors

- control-v1-0135 | Mamoa 1 dos Prados da Saba | score 76.89 | megalithic_mound
- control-v1-0200 | Castelo de Gaia | score 73.02 | historic_fortification;roman_built_context
- control-v1-0150 | Mámoa do Monte Penamá 1 | score 65.71 | megalithic_mound
- control-v1-0181 | Petróglifos do Campo da Mámoa | score 58.21 | megalithic_mound;rock_art_surface
- control-v1-0159 | A Torre do Braña/As Torres | score 56.80 | historic_fortification
- control-v1-0147 | Mámoa das Regas | score 51.00 | megalithic_mound
- control-v1-0118 | Fiães | score 50.21 | megalithic_mound
- control-v1-0144 | Arqueira de Morocos 2 | score 48.02 | megalithic_mound
- control-v1-0163 | Castelo Grande | score 45.90 | historic_fortification
- control-v1-0156 | Castelo da Modorra | score 45.84 | historic_fortification

## Failed Thumbnails

- control-v1-0172 | Xacemento da Torre do Hospital | HTTP Error 502: Bad Gateway

## Method

- Convert the RGB thumbnail to luminance.
- Compute Sobel edge magnitude.
- Estimate the provisional radius in pixels from the 512 m tile window.
- Compare edge and texture in the expected annulus against inner and outer context.
- Add angular coverage and radial-peak rank to avoid treating one isolated edge as a complete enclosure.

## Caution

High score means useful morphology signal for metric evaluation, not confirmed castro geometry.
Low score can also happen when vegetation, shadow, urban cover, crop timing or catalogue-point offset hide the structure in RGB orthophoto.
