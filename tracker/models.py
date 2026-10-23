from dataclasses import dataclass, field, asdict


@dataclass
class Job:
    source_id: str          # e.g. "wustl"
    job_id: str             # id unique within the source
    title: str
    url: str
    location: str = ""
    department: str = ""
    posted: str = ""        # ISO date if known, else the site's own text
    description: str = ""   # plain text, filled when details are fetched
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.source_id}:{self.job_id}"

    def to_dict(self):
        return asdict(self)
