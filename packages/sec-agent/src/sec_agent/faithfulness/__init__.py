"""Numeric faithfulness and citation checker: the last gate between the model and the user.

`check.check_answer` cuts an answer into sentences (`sentences`), reads every figure, date
and citation key of each one (`scan`), and traces each to the evidence of its turn
(`sources`, `trace`): a figure must equal a tool result in value, unit and period, or a
number of a passage the sentence cites. A sentence that holds anything untraced is
dropped; an answer that loses too much is blocked (`config`, `notices`). The report says
what was traced to what, so N2 counts answers whose every figure traced.
"""
