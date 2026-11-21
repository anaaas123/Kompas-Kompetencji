"""Reguły MC ze wskazaniem materiałów źródłowych."""

from kompas_core.slad import Regula
from kompas_core.zrodla import SourceRef
from pydantic import BaseModel, Field


class RegulaZAdnotacja(BaseModel):
    id: str
    adnotacje: list[SourceRef] = Field(min_length=1)

    def do_core(self) -> Regula:
        return Regula(self.id, self.adnotacje[0])
