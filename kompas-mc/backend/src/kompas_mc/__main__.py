"""Uruchomienie: ``uv run kompas-mc`` (port z KOMPAS_MC_PORT, domyślnie 8002)."""

import uvicorn

from .ustawienia import Ustawienia


def main() -> None:
    uvicorn.run("kompas_mc.app:app", host="127.0.0.1", port=Ustawienia.ze_srodowiska().port)


if __name__ == "__main__":
    main()
