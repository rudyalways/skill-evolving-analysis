# Frozen task cards

`tasks.json` is the frozen 10-task set generated from the golden skill contract.

Variants include normal publishing, long title, missing auth, publish timeout,
slug conflict, and duplicate title.

The runner prefers this file over regenerating tasks. Regenerate only when the
skill contract changes, then re-freeze and review.
