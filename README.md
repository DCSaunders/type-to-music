# type-to-music

Render simple SVG/PDF sheet music from an ABC-style shorthand string.

## Shorthand

```
[^|_|=]?[a-g][0-9]?
```

- `^` sharp, `_` flat, `=` natural (prefix, optional)
- `a`–`g` note letter (case-insensitive, required)
- single digit = octave (optional; defaults to 4, the middle-C octave)
- bare letters take the key signature — `c` in D major means C♯; write `=c` for a natural

## CLI

```sh
# C major scale, two octaves, as SVG
./sheet_music.py 'cdefgab c5 d5 e5 f5 g5 a5 b5 c6' -o scale.svg

# D major scale as PDF (key=2 → F♯ C♯ in the signature)
./sheet_music.py 'defgab c5 d5' -o d_major.pdf -k 2

# E♭ major (three flats), descending
./sheet_music.py 'e5 d5 c5 b a g f e' -o eb_descending.pdf -k -3

# Explicit accidentals: C♯4, B♭3, forced natural F in D major
./sheet_music.py '^c _b3 =f' -o accidentals.svg -k 2

# 3/4 time, custom width
./sheet_music.py 'cde fga b c5 d5 e5' -o waltz.pdf -t 3/4 -w 600
```

Output format is inferred from the extension (`.svg` or `.pdf`). Quote the
shorthand so the shell does not interpret `^` / `_` / `=` / digits.

## Library

```python
from sheet_music import save, save_pdf, parse, render

save('cdefgab c5', 'out.svg')
save_pdf('defgab c5 =f', 'd_major.pdf', key=2)

# Programmatic input
from sheet_music import note, rest
melody = [note('C4'), note('E4'), note('G4'), rest(4), note('C5', 2)]
save(melody, 'chord_with_rest.svg')
```

PDF output requires `cairosvg` (`pip install cairosvg`).
