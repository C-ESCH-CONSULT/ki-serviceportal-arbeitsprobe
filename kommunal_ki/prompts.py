"""Versionierte Prompt-Vorlagen. Jede Änderung ergibt eine neue Version, ältere bleiben abrufbar."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptVorlage:
    prompt_id: str
    version: str
    text: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]

    def fuellen(self, **werte: str) -> str:
        return self.text.format(**werte)


VORLAGEN: dict[tuple[str, str], PromptVorlage] = {}


def registrieren(vorlage: PromptVorlage) -> PromptVorlage:
    VORLAGEN[(vorlage.prompt_id, vorlage.version)] = vorlage
    return vorlage


def holen(prompt_id: str, version: str | None = None) -> PromptVorlage:
    if version:
        return VORLAGEN[(prompt_id, version)]
    passend = sorted((v for (pid, _), v in VORLAGEN.items() if pid == prompt_id), key=lambda v: int(v.version))
    if not passend:
        raise KeyError(prompt_id)
    return passend[-1]


registrieren(PromptVorlage("antwort_mit_quellen", "1", """\
Beantworte die Frage ausschließlich mit den nummerierten Quellen.
Nenne nach jeder Aussage die Quelle in eckigen Klammern, zum Beispiel [1].
Wenn die Quellen die Frage nicht beantworten, sage das ausdrücklich.

Quellen:
{quellen}

Frage: {frage}
Antwort:"""))

# Steht wörtlich in Version 2.
KEINE_ANGABEN = "Dazu enthält die Maßnahmensammlung keine Angaben."

registrieren(PromptVorlage("antwort_mit_quellen", "2", """\
Du unterstützt Mitarbeitende von Kommunen. Beantworte die Frage sachlich und knapp,
ausschließlich auf Grundlage der nummerierten Quellen. Nenne nach jeder Aussage die Quelle
in eckigen Klammern, zum Beispiel [1]. Erfinde keine Angaben. Wenn die Quellen die Frage
nicht beantworten, antworte genau mit: "Dazu enthält die Maßnahmensammlung keine Angaben."

Quellen:
{quellen}

Frage: {frage}
Antwort:"""))

registrieren(PromptVorlage("matching_begruendung", "1", """\
Erkläre in zwei Sätzen, warum die Maßnahme "{massnahme}" zum Bedarf der Kommune passt.
Bedarf: {bedarf}
Belege: {belege}
Begründung:"""))
