"""Capital-city questions answered in one word, as training and test examples under LOUPE_HOME.

uv run --all-extras python experiments/conditioning-methods/data.py
"""

from __future__ import annotations

from loupe.core import home
from loupe.data import Example, write_jsonl

CAPITALS = [
    ("France", "Paris"), ("Japan", "Tokyo"), ("Italy", "Rome"), ("Spain", "Madrid"),
    ("Germany", "Berlin"), ("Canada", "Ottawa"), ("Egypt", "Cairo"), ("Kenya", "Nairobi"),
    ("Peru", "Lima"), ("Chile", "Santiago"), ("Norway", "Oslo"), ("Sweden", "Stockholm"),
    ("Finland", "Helsinki"), ("Poland", "Warsaw"), ("Greece", "Athens"), ("Portugal", "Lisbon"),
    ("Austria", "Vienna"), ("Hungary", "Budapest"), ("Ireland", "Dublin"), ("Russia", "Moscow"),
    ("China", "Beijing"), ("India", "Delhi"), ("Thailand", "Bangkok"), ("Vietnam", "Hanoi"),
    ("Cuba", "Havana"), ("Mexico", "Mexico City"), ("Argentina", "Buenos Aires"),
    ("Colombia", "Bogota"), ("Denmark", "Copenhagen"), ("Belgium", "Brussels"),
    ("Netherlands", "Amsterdam"), ("Turkey", "Ankara"), ("Iran", "Tehran"), ("Iraq", "Baghdad"),
    ("Syria", "Damascus"), ("Ghana", "Accra"), ("Nigeria", "Abuja"), ("Morocco", "Rabat"),
    ("Australia", "Canberra"), ("New Zealand", "Wellington"), ("South Korea", "Seoul"),
    ("Indonesia", "Jakarta"), ("Philippines", "Manila"), ("Ukraine", "Kyiv"), ("Czechia", "Prague"),
]  # fmt: skip
TEST = 15  # the last countries, never trained on


def rows(pairs: list[tuple[str, str]]) -> list[Example]:
    return [Example(id=country, reply=capital,
                    messages=[{"role": "user", "content": f"What is the capital of {country}?"}])
            for country, capital in pairs]  # fmt: skip


def main() -> None:
    folder = home() / "data" / "conditioning-methods"
    write_jsonl(folder / "train.jsonl", rows(CAPITALS[:-TEST]))
    write_jsonl(folder / "test.jsonl", rows(CAPITALS[-TEST:]))
    print(folder)


if __name__ == "__main__":
    main()
