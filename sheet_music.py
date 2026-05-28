#!/usr/bin/env python3
"""Render simple SVG sheet music.

>>> from sheet_music import save, save_pdf, parse, render
>>> save('cdefgab c5', 'out.svg')             # accepts a shorthand string directly
>>> save_pdf('defgab ^c5', 'd_major.pdf', key=2)

Pitch (note()):
    Scientific pitch notation, e.g. 'C4', 'F#5', 'Bb3'.
    Add an 'n' (e.g. 'Cn4') to force a natural sign even in a key without one.

Shorthand (parse() — ABC-style):
    [accidental][letter][octave-digit]
        ^ = sharp,  _ = flat,  = = natural   (prefix, optional)
        a-g letter, case-insensitive          (required)
        single digit                          (optional; defaults to 4)
    A bare letter (no octave digit) sits in the octave starting at middle C
    (so `c` is middle C = C4, `b` is B4). Use `c5`, `c3`, etc. for other octaves.
    A bare letter (no accidental) takes its accidental from the key signature,
    matching ABC semantics — so `c` in D major means C#. Write `=c` to force
    a natural. Whitespace and commas are ignored. All notes are quarter notes.

Duration: 1=whole, 2=half, 4=quarter, 8=eighth, 16=sixteenth.

Key signature:
    `key` is the number of sharps (positive) or flats (negative).
    e.g. key=2 → D major (F#, C#); key=-3 → Eb major (Bb, Eb, Ab).

render(), save(), save_pdf() accept either a list of elements or a shorthand
string. When given a string, `key` is passed to the parser as well.
"""

from typing import Dict, Iterable, List, Tuple

NOTE_LETTERS = 'CDEFGAB'

# Layout (px)
LS = 8
STAFF_H = LS * 4
STAFF_GAP = 56
MARGIN_L = 16
MARGIN_R = 16
MARGIN_T = 32
MARGIN_B = 16

CLEF_W = 40
TIMESIG_W = 26
NOTE_W = 28
BAR_W = 12
KEYSIG_ACC_W = LS * 1.0

STEM_LEN = LS * 3.25
HEAD_RX = LS * 0.65
HEAD_RY = LS * 0.5
STEM_W = 1.2

# Key signature accidental positions (in treble clef)
KEY_SHARP_PITCHES = ['F5', 'C5', 'G5', 'D5', 'A4', 'E5', 'B4']
KEY_FLAT_PITCHES = ['B4', 'E5', 'A4', 'D5', 'G4', 'C5', 'F4']


# ---- public API ----------------------------------------------------------

def note(pitch: str, duration: int = 4) -> Dict:
    return {'kind': 'note', 'pitch': pitch, 'duration': duration}


def rest(duration: int = 4) -> Dict:
    return {'kind': 'rest', 'duration': duration}


def barline() -> Dict:
    return {'kind': 'barline'}


def parse(text: str, key: int = 0) -> List[Dict]:
    """Parse ABC-style shorthand into a list of (quarter-note) note elements.

    Token: [^|_|=]?[a-g][0-9]?   — accidental, letter, optional octave digit.
    A bare letter takes the key signature's accidental ('c' in D major = C#).
    """
    text = text.lower()
    out: List[Dict] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace() or ch == ',':
            i += 1
            continue
        explicit = ''
        if ch in '^_=':
            explicit = ch
            i += 1
        if i >= n or text[i] not in 'abcdefg':
            raise ValueError(f'Expected note letter at position {i} in {text!r}')
        letter = text[i].upper()
        i += 1
        octave = 4
        if i < n and text[i].isdigit():
            octave = int(text[i])
            i += 1
        if explicit == '^':
            acc = '#'
        elif explicit == '_':
            acc = 'b'
        elif explicit == '=':
            acc = 'n'
        else:
            acc = _key_acc_for_letter(letter, key)
        out.append(note(f'{letter}{acc}{octave}'))
    return out


def render(input, *,
           time_signature: Tuple[int, int] = (4, 4),
           key: int = 0,
           width: int = 800) -> str:
    """Render to an SVG document string. `input` is a list of elements or a shorthand string."""
    if isinstance(input, str):
        input = parse(input, key=key)
    elements = list(input)
    elements = _auto_barlines(elements, time_signature)
    while elements and elements[-1]['kind'] == 'barline':
        elements.pop()
    keysig_w = abs(key) * KEYSIG_ACC_W
    lines = _wrap(elements, width, keysig_w)
    return _draw(lines, time_signature, key, keysig_w, width)


def save(input, path: str, **kwargs) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(render(input, **kwargs))


def save_pdf(input, path: str, **kwargs) -> None:
    """Render to PDF. Requires `cairosvg`."""
    import cairosvg
    svg = render(input, **kwargs)
    cairosvg.svg2pdf(bytestring=svg.encode('utf-8'), write_to=path)


# ---- pitch helpers -------------------------------------------------------

def _step(pitch: str) -> int:
    letter = pitch[0].upper()
    tail = pitch[1:]
    if tail and tail[0] in '#bn':
        tail = tail[1:]
    return int(tail) * 7 + NOTE_LETTERS.index(letter)


def _accidental(pitch: str) -> str:
    return pitch[1] if len(pitch) > 1 and pitch[1] in '#bn' else ''


_F5 = _step('F5')
_E4 = _step('E4')
_B4 = _step('B4')


def _key_acc_for_letter(letter: str, key: int) -> str:
    """Accidental the key signature provides for this letter, or ''."""
    L = letter.upper()
    if key > 0:
        for p in KEY_SHARP_PITCHES[:min(key, 7)]:
            if p[0] == L:
                return '#'
    elif key < 0:
        for p in KEY_FLAT_PITCHES[:min(-key, 7)]:
            if p[0] == L:
                return 'b'
    return ''


def _displayed_accidental(pitch: str, key: int) -> str:
    """Accidental to draw on this note: '', '#', 'b', or 'n' (natural)."""
    pitch_acc = _accidental(pitch)
    key_acc = _key_acc_for_letter(pitch[0], key)
    if pitch_acc == 'n':
        return 'n' if key_acc != '' else ''
    if pitch_acc == key_acc:
        return ''
    if pitch_acc == '' and key_acc != '':
        return 'n'
    return pitch_acc


# ---- layout --------------------------------------------------------------

def _beats(d: int) -> float:
    return 4.0 / d


def _element_width(el: Dict) -> float:
    return BAR_W if el['kind'] == 'barline' else NOTE_W


def _auto_barlines(elements: List[Dict], time_sig: Tuple[int, int]) -> List[Dict]:
    beats_per_bar = time_sig[0] * (4.0 / time_sig[1])
    out: List[Dict] = []
    acc = 0.0
    for el in elements:
        if el['kind'] == 'barline':
            out.append(el)
            acc = 0.0
            continue
        out.append(el)
        if el['kind'] in ('note', 'rest'):
            acc += _beats(el['duration'])
            if acc >= beats_per_bar - 1e-9:
                out.append(barline())
                acc = 0.0
    return out


def _wrap(elements: List[Dict], page_width: int, keysig_w: float) -> List[List[Dict]]:
    content_w = page_width - MARGIN_L - MARGIN_R
    first_avail = content_w - CLEF_W - keysig_w - TIMESIG_W
    other_avail = content_w - CLEF_W - keysig_w
    lines: List[List[Dict]] = []
    current: List[Dict] = []
    used = 0.0
    avail = first_avail
    for el in elements:
        w = _element_width(el)
        if used + w > avail and current:
            lines.append(current)
            current = []
            used = 0.0
            avail = other_avail
        current.append(el)
        used += w
    if current:
        lines.append(current)
    return lines


# ---- SVG drawing primitives ----------------------------------------------

def _staff(x0: float, x1: float, top_y: float) -> List[str]:
    return [
        f'<line x1="{x0}" y1="{top_y + i * LS}" x2="{x1}" y2="{top_y + i * LS}" '
        f'stroke="black" stroke-width="1"/>'
        for i in range(5)
    ]


def _clef(x_left: float, top_y: float) -> List[str]:
    """Stylized treble clef, anchored around the G4 line."""
    cx = x_left + CLEF_W * 0.45
    g4y = top_y + 3 * LS
    s = LS
    d = (
        f'M {cx + 0.4*s} {g4y - 4.0*s} '
        f'Q {cx + 1.3*s} {g4y - 4.2*s}, {cx + 0.8*s} {g4y - 3.0*s} '
        f'Q {cx + 0.3*s} {g4y - 2.0*s}, {cx - 0.4*s} {g4y - 1.0*s} '
        f'Q {cx - 1.8*s} {g4y - 0.6*s}, {cx - 1.6*s} {g4y + 0.6*s} '
        f'Q {cx - 1.4*s} {g4y + 1.6*s}, {cx - 0.1*s} {g4y + 1.3*s} '
        f'Q {cx + 1.3*s} {g4y + 0.7*s}, {cx + 0.7*s} {g4y - 0.4*s} '
        f'Q {cx + 0.1*s} {g4y - 0.7*s}, {cx + 0.1*s} {g4y + 0.2*s} '
        f'L {cx + 0.4*s} {g4y + 3.0*s} '
        f'Q {cx + 0.4*s} {g4y + 3.5*s}, {cx - 0.4*s} {g4y + 3.2*s} '
    )
    return [
        f'<path d="{d}" fill="none" stroke="black" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/>',
        f'<circle cx="{cx - 0.5*s}" cy="{g4y + 3.2*s}" r="{0.28*s}" fill="black"/>',
    ]


def _timesig(x_center: float, top_y: float, top: int, bottom: int) -> List[str]:
    style = (f'font-family="DejaVu Serif, Times, serif" font-size="{LS * 2.4}" '
             f'font-weight="bold" text-anchor="middle"')
    return [
        f'<text x="{x_center}" y="{top_y + LS * 1.7}" {style}>{top}</text>',
        f'<text x="{x_center}" y="{top_y + LS * 3.7}" {style}>{bottom}</text>',
    ]


def _barline(x: float, top_y: float) -> List[str]:
    return [
        f'<line x1="{x}" y1="{top_y}" x2="{x}" y2="{top_y + STAFF_H}" '
        f'stroke="black" stroke-width="1.2"/>'
    ]


def _final_barline(x: float, top_y: float) -> List[str]:
    return [
        f'<line x1="{x}" y1="{top_y}" x2="{x}" y2="{top_y + STAFF_H}" '
        f'stroke="black" stroke-width="1"/>',
        f'<line x1="{x + 4}" y1="{top_y}" x2="{x + 4}" y2="{top_y + STAFF_H}" '
        f'stroke="black" stroke-width="3"/>',
    ]


def _note_y(pitch: str, top_y: float) -> float:
    return top_y + (_F5 - _step(pitch)) * (LS / 2)


def _ledger(x: float, top_y: float, pitch: str) -> List[str]:
    s = _step(pitch)
    out: List[str] = []
    ext = HEAD_RX * 1.6
    if s >= _F5 + 2:
        for step in range(_F5 + 2, s + 1, 2):
            y = top_y - (step - _F5) * (LS / 2)
            out.append(f'<line x1="{x - ext}" y1="{y}" x2="{x + ext}" y2="{y}" '
                       f'stroke="black" stroke-width="1"/>')
    elif s <= _E4 - 2:
        for step in range(_E4 - 2, s - 1, -2):
            y = top_y + STAFF_H + (_E4 - step) * (LS / 2)
            out.append(f'<line x1="{x - ext}" y1="{y}" x2="{x + ext}" y2="{y}" '
                       f'stroke="black" stroke-width="1"/>')
    return out


# ---- accidental glyphs (drawn as paths) ----------------------------------

def _sharp_glyph(cx: float, cy: float) -> List[str]:
    s = LS
    parts = []
    for dx in (-0.4*s, 0.4*s):
        parts.append(
            f'<line x1="{cx + dx}" y1="{cy - 1.05*s}" x2="{cx + dx}" '
            f'y2="{cy + 1.05*s}" stroke="black" stroke-width="1"/>'
        )
    bar_h = 0.28*s
    for dy in (-0.38*s, 0.38*s):
        x1, x2 = cx - 0.7*s, cx + 0.7*s
        y_l, y_r = cy + dy + 0.12*s, cy + dy - 0.12*s
        parts.append(
            f'<polygon points="{x1},{y_l - bar_h/2} {x2},{y_r - bar_h/2} '
            f'{x2},{y_r + bar_h/2} {x1},{y_l + bar_h/2}" fill="black"/>'
        )
    return parts


def _flat_glyph(cx: float, cy: float) -> List[str]:
    s = LS
    stem_x = cx - 0.35*s
    return [
        f'<line x1="{stem_x}" y1="{cy - 1.5*s}" x2="{stem_x}" '
        f'y2="{cy + 0.5*s}" stroke="black" stroke-width="1.5"/>',
        f'<path d="M {stem_x} {cy - 0.35*s} '
        f'Q {cx + 0.85*s} {cy - 0.6*s}, {cx + 0.55*s} {cy + 0.15*s} '
        f'Q {cx + 0.0*s} {cy + 0.7*s}, {stem_x} {cy + 0.3*s} Z" '
        f'fill="black"/>',
    ]


def _natural_glyph(cx: float, cy: float) -> List[str]:
    s = LS
    parts = [
        f'<line x1="{cx - 0.3*s}" y1="{cy - 1.05*s}" x2="{cx - 0.3*s}" '
        f'y2="{cy + 0.65*s}" stroke="black" stroke-width="1"/>',
        f'<line x1="{cx + 0.3*s}" y1="{cy - 0.65*s}" x2="{cx + 0.3*s}" '
        f'y2="{cy + 1.05*s}" stroke="black" stroke-width="1"/>',
    ]
    bar_h = 0.22*s
    for dy in (-0.3*s, 0.3*s):
        x1, x2 = cx - 0.3*s, cx + 0.3*s
        y_l, y_r = cy + dy + 0.08*s, cy + dy - 0.08*s
        parts.append(
            f'<polygon points="{x1},{y_l - bar_h/2} {x2},{y_r - bar_h/2} '
            f'{x2},{y_r + bar_h/2} {x1},{y_l + bar_h/2}" fill="black"/>'
        )
    return parts


def _accidental_at(cx: float, cy: float, kind: str) -> List[str]:
    if kind == '#':
        return _sharp_glyph(cx, cy)
    if kind == 'b':
        return _flat_glyph(cx, cy)
    if kind == 'n':
        return _natural_glyph(cx, cy)
    return []


# ---- key signature --------------------------------------------------------

def _key_signature(x_left: float, top_y: float, key: int) -> List[str]:
    if key == 0:
        return []
    pitches = KEY_SHARP_PITCHES if key > 0 else KEY_FLAT_PITCHES
    kind = '#' if key > 0 else 'b'
    parts: List[str] = []
    for i in range(min(abs(key), 7)):
        cx = x_left + (i + 0.5) * KEYSIG_ACC_W
        cy = _note_y(pitches[i], top_y)
        parts += _accidental_at(cx, cy, kind)
    return parts


# ---- flags ---------------------------------------------------------------

def _flag(x_stem: float, y_tip: float, up: bool, count: int) -> List[str]:
    out: List[str] = []
    for i in range(count):
        if up:
            y0 = y_tip + i * LS * 1.0
            d = (f'M {x_stem} {y0} '
                 f'q {LS * 1.1} {LS * 0.6} {LS * 1.4} {LS * 2.0} '
                 f'q {-LS * 0.2} {-LS * 0.5} {-LS * 1.4} {-LS * 1.2} z')
        else:
            y0 = y_tip - i * LS * 1.0
            d = (f'M {x_stem} {y0} '
                 f'q {LS * 1.1} {-LS * 0.6} {LS * 1.4} {-LS * 2.0} '
                 f'q {-LS * 0.2} {LS * 0.5} {-LS * 1.4} {LS * 1.2} z')
        out.append(f'<path d="{d}" fill="black"/>')
    return out


# ---- notes & rests --------------------------------------------------------

def _note_svg(x: float, top_y: float, el: Dict, key: int) -> List[str]:
    pitch = el['pitch']
    duration = el['duration']
    y = _note_y(pitch, top_y)
    out: List[str] = []

    disp_acc = _displayed_accidental(pitch, key)
    if disp_acc:
        out += _accidental_at(x - HEAD_RX - LS * 0.6, y, disp_acc)

    out += _ledger(x, top_y, pitch)

    filled = duration >= 4
    out.append(
        f'<ellipse cx="{x}" cy="{y}" rx="{HEAD_RX}" ry="{HEAD_RY}" '
        f'fill="{"black" if filled else "white"}" stroke="black" stroke-width="1.2"/>'
    )

    if duration >= 2:
        up = _step(pitch) < _B4
        if up:
            sx = x + HEAD_RX - STEM_W / 2
            sy_tip = y - STEM_LEN
        else:
            sx = x - HEAD_RX + STEM_W / 2
            sy_tip = y + STEM_LEN
        out.append(
            f'<line x1="{sx}" y1="{y}" x2="{sx}" y2="{sy_tip}" '
            f'stroke="black" stroke-width="{STEM_W}"/>'
        )
        if duration >= 8:
            out += _flag(sx, sy_tip, up, 1 if duration == 8 else 2)
    return out


def _rest_svg(x: float, top_y: float, el: Dict) -> List[str]:
    duration = el['duration']
    s = LS
    if duration == 1:
        d5_y = top_y + LS
        return [f'<rect x="{x - 0.8*s}" y="{d5_y}" width="{1.6*s}" '
                f'height="{0.55*s}" fill="black"/>']
    if duration == 2:
        b4_y = top_y + 2 * LS
        return [f'<rect x="{x - 0.8*s}" y="{b4_y - 0.55*s}" width="{1.6*s}" '
                f'height="{0.55*s}" fill="black"/>']
    if duration == 4:
        cy = top_y + STAFF_H / 2
        d = (
            f'M {x - 0.6*s} {cy - 1.8*s} '
            f'L {x + 0.5*s} {cy - 0.6*s} '
            f'L {x - 0.4*s} {cy + 0.3*s} '
            f'L {x + 0.5*s} {cy + 1.4*s} '
            f'Q {x - 0.1*s} {cy + 0.8*s}, {x - 0.2*s} {cy + 1.9*s}'
        )
        return [f'<path d="{d}" fill="none" stroke="black" stroke-width="2" '
                f'stroke-linecap="round" stroke-linejoin="round"/>']
    if duration in (8, 16):
        cy = top_y + STAFF_H / 2
        n_flags = 1 if duration == 8 else 2
        top_y0 = cy - 1.2 * s if duration == 8 else cy - 1.6 * s
        bot_y0 = cy + 1.4 * s if duration == 8 else cy + 1.8 * s
        parts = [
            f'<line x1="{x + 0.5*s}" y1="{top_y0}" x2="{x - 0.4*s}" '
            f'y2="{bot_y0}" stroke="black" stroke-width="1.4"/>'
        ]
        for k in range(n_flags):
            dy = k * 0.9 * s
            parts.append(
                f'<circle cx="{x + 0.45*s - k*0.2*s}" cy="{cy - 0.6*s + dy}" '
                f'r="{0.32*s}" fill="black"/>'
            )
            parts.append(
                f'<path d="M {x + 0.6*s} {top_y0 + dy} '
                f'Q {x + 1.05*s} {cy - 0.7*s + dy}, {x + 0.25*s} {cy - 0.4*s + dy}" '
                f'fill="none" stroke="black" stroke-width="1.3"/>'
            )
        return parts
    return []


# ---- compose -------------------------------------------------------------

def _draw(lines: List[List[Dict]], time_sig: Tuple[int, int], key: int,
          keysig_w: float, page_width: int) -> str:
    height = int(MARGIN_T + len(lines) * (STAFF_H + STAFF_GAP) + MARGIN_B)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_width}" '
        f'height="{height}" viewBox="0 0 {page_width} {height}">',
        f'<rect width="{page_width}" height="{height}" fill="white"/>',
    ]
    x1 = page_width - MARGIN_R
    for li, line in enumerate(lines):
        top_y = MARGIN_T + li * (STAFF_H + STAFF_GAP)
        x0 = MARGIN_L
        parts += _staff(x0, x1, top_y)

        x = x0 + 4
        parts += _clef(x, top_y)
        x += CLEF_W

        if key != 0:
            parts += _key_signature(x, top_y, key)
            x += keysig_w

        if li == 0:
            parts += _timesig(x + TIMESIG_W / 2, top_y, time_sig[0], time_sig[1])
            x += TIMESIG_W

        for el in line:
            if el['kind'] == 'barline':
                parts += _barline(x + BAR_W / 2, top_y)
                x += BAR_W
            elif el['kind'] == 'note':
                parts += _note_svg(x + NOTE_W / 2, top_y, el, key)
                x += NOTE_W
            elif el['kind'] == 'rest':
                parts += _rest_svg(x + NOTE_W / 2, top_y, el)
                x += NOTE_W

        if li == len(lines) - 1:
            parts += _final_barline(x + 2, top_y)
        else:
            parts += _barline(x1, top_y)

    parts.append('</svg>')
    return '\n'.join(parts)


def _cli():
    import argparse
    p = argparse.ArgumentParser(
        description='Render ABC-style shorthand into SVG or PDF sheet music.',
        epilog='Shorthand: ^ sharp, _ flat, = natural (prefix); a-g letter; optional digit = octave. '
               'Default octave is 4 (middle-C octave). Bare letters take the key signature.',
    )
    p.add_argument('notes', help='shorthand string, e.g. "cdefgab c5" or "^c _b3 =f"')
    p.add_argument('-o', '--output', required=True, help='output file (.svg or .pdf)')
    p.add_argument('-k', '--key', type=int, default=0,
                   help='key signature: positive=sharps, negative=flats (default 0)')
    p.add_argument('-t', '--time', default='4/4', metavar='N/D',
                   help='time signature (default 4/4)')
    p.add_argument('-w', '--width', type=int, default=800,
                   help='page width in px (default 800)')
    args = p.parse_args()
    try:
        num, den = (int(x) for x in args.time.split('/'))
    except ValueError:
        p.error(f'invalid time signature {args.time!r}, expected N/D like 3/4')
    kwargs = dict(key=args.key, time_signature=(num, den), width=args.width)
    writer = save_pdf if args.output.lower().endswith('.pdf') else save
    writer(args.notes, args.output, **kwargs)
    print(f'wrote {args.output}')


if __name__ == '__main__':
    _cli()
