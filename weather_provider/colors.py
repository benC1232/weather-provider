"""Temperature colors, after Wikipedia's climate tables.

Wikipedia's formula (Module:Weather box/colors, _temperature_color) runs
blue (-42.75 °C) -> white (4.5 °C) -> orange (23 °C) -> red (41.5 °C). The sign
this was built for rarely sees freezing, so the cold half is squeezed: fully blue
at BLUE_AT, white at WHITE_AT. The warm half keeps Wikipedia's shape from
WHITE_AT up to red at 41.5 °C.
"""

BLUE_AT = 5.0
WHITE_AT = 15.0

_WIKI_BLUE = -42.75
_WIKI_WHITE = 4.5
_WIKI_RED = 41.5


def _range_pos(value, start, stop):
    """Wikipedia's range_pos: 0 at start, 1 at stop, clamped."""
    if start < stop:
        return min(1.0, max(0.0, (value - start) / (stop - start)))
    return min(1.0, max(0.0, (start - value) / (start - stop)))


def _to_wiki_scale(t):
    """Map our temperature onto the point Wikipedia's formula would color the same."""
    if t <= WHITE_AT:
        f = (t - BLUE_AT) / (WHITE_AT - BLUE_AT)
        return _WIKI_BLUE + f * (_WIKI_WHITE - _WIKI_BLUE)
    f = (t - WHITE_AT) / (_WIKI_RED - WHITE_AT)
    return _WIKI_WHITE + f * (_WIKI_RED - _WIKI_WHITE)


def temperature_color(t):
    """(r, g, b) for a temperature in °C."""
    v = min(_to_wiki_scale(t), _WIKI_RED)  # past red Wikipedia darkens, which vanishes on black
    if v < _WIKI_WHITE:
        r = g = _range_pos(v, _WIKI_BLUE, _WIKI_WHITE)
        b = 1.0
    else:
        r = 1.0
        g = _range_pos(v, _WIKI_RED, _WIKI_WHITE)
        b = _range_pos(v, 23, _WIKI_WHITE)
    return round(r * 255), round(g * 255), round(b * 255)
