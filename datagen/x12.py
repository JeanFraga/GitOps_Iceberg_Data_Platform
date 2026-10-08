"""Minimal stdlib X12 005010 writer and round-trip parser. Not certified against any guide."""

from __future__ import annotations

from dataclasses import dataclass, field

ELEMENT, COMPONENT, REPETITION, TERMINATOR = "*", ":", "^", "~"
MAX_PER_ST = 500


def segment(*elements: str) -> str:
    """Join elements, dropping trailing empty ones."""
    parts = list(elements)
    while parts and parts[-1] == "":
        parts.pop()
    return ELEMENT.join(parts)


@dataclass
class Interchange:
    sender: str
    receiver: str
    date: str  # CCYYMMDD
    time: str  # HHMM
    version: str  # e.g. 005010X222A1
    control: int = 1
    functional_id: str = "HC"
    transactions: list[list[str]] = field(default_factory=list)

    def add(self, body: list[str]) -> None:
        """Body segments between ST and SE (exclusive)."""
        self.transactions.append(body)

    def render(self) -> bytes:
        icn = f"{self.control:09d}"
        isa = segment(
            "ISA", "00", " " * 10, "00", " " * 10, "ZZ", self.sender.ljust(15), "ZZ", self.receiver.ljust(15),
            self.date[2:], self.time, REPETITION, "00501", icn, "0", "T", COMPONENT,
        )  # fmt: skip
        assert len(isa) + 1 == 106, len(isa)
        segs = [isa, segment("GS", self.functional_id, self.sender, self.receiver, self.date, self.time,
                             str(self.control), "X", self.version)]  # fmt: skip
        for i, body in enumerate(self.transactions, 1):
            st = f"{i:04d}"
            segs.append(segment("ST", "837", st, self.version))
            segs.extend(body)
            segs.append(segment("SE", str(len(body) + 2), st))
        segs.append(segment("GE", str(len(self.transactions)), str(self.control)))
        segs.append(segment("IEA", "1", icn))
        return "".join(s + TERMINATOR + "\n" for s in segs).encode()


def parse(data: bytes) -> list[list[str]]:
    """Split into segments of elements using the delimiters the ISA declares."""
    text = data.decode()
    if not text.startswith("ISA"):
        raise ValueError("not an X12 interchange")
    elem, term = text[3], text[105]
    return [s.strip().split(elem) for s in text.split(term) if s.strip()]
