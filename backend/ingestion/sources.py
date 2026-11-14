from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol
from types import MappingProxyType


@dataclass(frozen=True)
class SourceRecord:
    source_key: str
    values: Mapping[str, object]


class ReadOnlySource(Protocol):
    def read(self) -> Iterable[SourceRecord]: ...


class CarthagoReadOnlySource:
    def read(self) -> Iterable[SourceRecord]:
        raise NotImplementedError(
            "Interface Carthago non approuvée ; intégration désactivée."
        )


class SyntheticReadOnlySource:
    """Explicit fixture adapter, not a claim about Carthago's approved schema.

    Consumers receive immutable synthetic records; this adapter has no write API,
    network connection or automatic path into authoritative domain tables.
    """

    source = "SYNTHETIC_ONLY"
    version = "synthetic-v1"

    def read(self) -> Iterable[SourceRecord]:
        return (
            SourceRecord(
                source_key="SYNTHETIC-SNAPSHOT-001",
                values=MappingProxyType(
                    {
                        "label": "Enregistrement source synthétique",
                        "fixture_version": self.version,
                    }
                ),
            ),
        )


class ManualExcelSource:
    def read(self) -> Iterable[SourceRecord]:
        raise NotImplementedError(
            "Parsing différé après validation des modèles et des contrôles de fichiers."
        )
