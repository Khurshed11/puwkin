import re
from dataclasses import dataclass


@dataclass
class SizeRange:
    size: str
    height_min: float | None = None
    height_max: float | None = None
    weight_min: float | None = None
    weight_max: float | None = None


def parse_size_chart(size_chart: str) -> list[SizeRange]:
    """
    Парсит текстовую размерную сетку товара.

    Ожидаемый формат строки замеров (одна или несколько строк):
        "M (170-175см, 65-72кг), L (175-180см, 73-80кг), XL (180-188см, 81-90кг)"

    Возвращает список SizeRange. Если распарсить не удалось — пустой список.
    """
    ranges: list[SizeRange] = []

    # Ищем шаблоны вида: РАЗМЕР (РОСТ-РОСТсм, ВЕС-ВЕСкг)
    # Рост и вес опциональны (могут быть только рост или только вес).
    pattern = re.compile(
        r"([A-Za-zА-Яа-я]{1,4})\s*"          # размер: M, L, XL...
        r"\(\s*"
        r"(?:(\d{2,3})\s*[-–]\s*(\d{2,3})\s*(?:см|cm))?"  # рост 170-175см
        r"\s*,?\s*"
        r"(?:(\d{2,3})\s*[-–]\s*(\d{2,3})\s*(?:кг|kg))?"  # вес 65-72кг
        r"\s*\)",
        re.IGNORECASE,
    )

    for m in pattern.finditer(size_chart):
        size = m.group(1).upper()
        h_min, h_max, w_min, w_max = m.group(2), m.group(3), m.group(4), m.group(5)
        ranges.append(
            SizeRange(
                size=size,
                height_min=float(h_min) if h_min else None,
                height_max=float(h_max) if h_max else None,
                weight_min=float(w_min) if w_min else None,
                weight_max=float(w_max) if w_max else None,
            )
        )

    return ranges


def recommend_size(
    size_chart: str, height: float, weight: float
) -> tuple[str | None, str]:
    """
    Подбирает размер по росту (см) и весу (кг).

    Возвращает кортеж (рекомендованный_размер или None, пояснение).
    """
    ranges = parse_size_chart(size_chart)

    if not ranges:
        return None, (
            "Не удалось автоматически подобрать размер по замерам этого товара.\n\n"
            "Пожалуйста, сверьтесь с размерной сеткой в карточке товара или "
            "напишите менеджеру — он поможет с выбором."
        )

    # 1) Ищем идеальное попадание: и рост, и вес в диапазоне.
    ideal = [
        r
        for r in ranges
        if _in_range(height, r.height_min, r.height_max)
        and _in_range(weight, r.weight_min, r.weight_max)
    ]
    if ideal:
        r = ideal[0]
        return r.size, (
            f"Вам идеально подойдёт размер <b>{r.size}</b>.\n"
            f"Подходит под рост {_fmt_range(r.height_min, r.height_max, 'см')} "
            f"и вес {_fmt_range(r.weight_min, r.weight_max, 'кг')}."
        )

    # 2) Ближайший размер по «очкам» близости (работает и для выходящих
    #    за сетку параметров — выберет наименьший или наибольший размер).
    best = max(ranges, key=lambda r: _score_range(r, height, weight))

    # Определяем, пользователь «меньше» или «больше» ближайшего диапазона.
    smaller = _user_is_smaller_than(best, height, weight)

    if smaller:
        return best.size, (
            f"Ваши параметры немного меньше размерной сетки.\n"
            f"Ближе всего — размер <b>{best.size}</b> "
            f"(рост {_fmt_range(best.height_min, best.height_max, 'см')}, "
            f"вес {_fmt_range(best.weight_min, best.weight_max, 'кг')}).\n\n"
            "Если предпочитаете свободную посадку — берите на размер больше."
        )
    else:
        return best.size, (
            f"Ваши параметры немного больше размерной сетки.\n"
            f"Ближе всего — размер <b>{best.size}</b> "
            f"(рост {_fmt_range(best.height_min, best.height_max, 'см')}, "
            f"вес {_fmt_range(best.weight_min, best.weight_max, 'кг')}).\n\n"
            "Это хороший выбор для комфортной, слегка свободной посадки."
        )


def _user_is_smaller_than(r: SizeRange, height: float, weight: float) -> bool:
    """True, если параметры пользователя ниже диапазона (по ведущему показателю)."""
    # Приоритет — рост, иначе вес.
    if r.height_min is not None or r.height_max is not None:
        lo = r.height_min if r.height_min is not None else r.height_max
        hi = r.height_max if r.height_max is not None else r.height_min
        mid = (lo + hi) / 2
        return height < mid
    if r.weight_min is not None or r.weight_max is not None:
        lo = r.weight_min if r.weight_min is not None else r.weight_max
        hi = r.weight_max if r.weight_max is not None else r.weight_min
        mid = (lo + hi) / 2
        return weight < mid
    return False


def _in_range(value: float, v_min: float | None, v_max: float | None) -> bool:
    if v_min is None and v_max is None:
        return True
    if v_min is not None and value < v_min:
        return False
    if v_max is not None and value > v_max:
        return False
    return True


def _score_range(r: SizeRange, height: float, weight: float) -> float:
    """Очки близости: 2.0 = оба параметра попали, 1.0 = один, иначе штраф."""
    score = 0.0
    for value, v_min, v_max in (
        (height, r.height_min, r.height_max),
        (weight, r.weight_min, r.weight_max),
    ):
        if v_min is None and v_max is None:
            continue
        if _in_range(value, v_min, v_max):
            score += 1.0
        else:
            # Чем дальше от диапазона — тем сильнее штраф
            dist = 0.0
            if v_min is not None:
                dist = max(dist, v_min - value)
            if v_max is not None:
                dist = max(dist, value - v_max)
            score -= min(dist / 10.0, 3.0)
    return score


def _fmt_range(v_min: float | None, v_max: float | None, unit: str) -> str:
    if v_min is not None and v_max is not None:
        return f"{int(v_min)}-{int(v_max)} {unit}"
    if v_min is not None:
        return f"от {int(v_min)} {unit}"
    if v_max is not None:
        return f"до {int(v_max)} {unit}"
    return "—"
