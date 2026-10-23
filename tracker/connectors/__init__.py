"""Each connector exposes:
    search(http, src, terms, title_ok) -> list[Job]   list pages only (cheap)
    details(http, src, job) -> Job                    fills job.description for one job
`title_ok` lets a connector skip detail-level work for titles that will be dropped anyway.
"""
from . import workday, oracle, eightfold, rmk, jibe, mcloud, taleo, html_list, ucrecruit, smartrecruiters

REGISTRY = {
    "smartrecruiters": smartrecruiters,
    "workday": workday,
    "oracle": oracle,
    "eightfold": eightfold,
    "rmk": rmk,
    "jibe": jibe,
    "mcloud": mcloud,
    "taleo": taleo,
    "html_list": html_list,
    "ucrecruit": ucrecruit,
}
