# New data format

Turn a labeled trace set into one cluster record the next step can match. This is the Cluster state. It is not on the current machine, so it has no step number. The numbered folders are the run.

## Experience

Start from a small selection, then expand with skills that share the same label. The cluster output is Jev-compatible so a later match can compare trace structure with skill label metadata.

## Don't

Do not emit one record per raw trace. Do not drop the label that the expansion used. Do not invent a format the selector cannot read.

## Must

Write one cluster per next step. Keep the shared label, the traces in the cluster, and the candidate skills that carry that label.

## Applies when

Traces are labeled and ready to cluster, before skill selection.
