# Completion check

Require a non-empty final answer before treating the turn as done when the user question is still open.

The question stays unfinished when the outcome is aborted, the assistant text is empty, and there is no infrastructure failure. A stated choice that answers the question, such as a new project versus a new database, satisfies the check. Empty assistant text does not.
