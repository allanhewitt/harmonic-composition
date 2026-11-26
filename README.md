# Harmonic Composition

A generator that writes long harmonic structures and the parts that sit on them, as source material to improvise over
and develop in Logic. The composer sets parameters; the machine makes every chord and note decision.

**Status:** Stage 1. Song, structure, harmony, pads, a shared density plan, a Moog 960-style bass, three lines, a density filter,
score engraving and MIDI files. Stage 2 (the ten sequencer models, rhythm-first composition, line embellishments,
per-section settings, live MIDI) is planned in [docs/roadmap.md](docs/roadmap.md).

## Pipeline

| Step | What it does | Module |
| --- | --- | --- |
| 1 Song | Title, key (seven modes), tempo, meter, length target, seed | `composition_generator.py` |
| 2 Structure | Sections and phrases from nine form models; repeats keep their shape | `gcl_structure.py` (GCL Version One v0.3) |
| 3 Harmony | Chords from corpus-measured models (Billboard, Beatles, jazz); 0.5 settings reproduce measured behaviour | `harmonic_engine.py` |
| 4 Parts | Pads, density plan, bass, lines, density filter | `parts.py`, `orchestration.py`, `bass960.py`, `lines.py`, `thinning.py` |
| 5 Output | Score (LilyPond PDF), MIDI per part plus combined, resolved script | `notation.py`, `midi_export.py` |

A **piece script** (YAML) holds every setting. The web app builds the script from menus; the command line runs one directly.
Each run writes `<stem>_resolved.yaml` with every default filled in, so any result can be rebuilt exactly.

## Use

**Web app** (what Coolify runs):

```sh
pip install -r requirements.txt
HC_DATA_DIR=./data PORT=3000 python app/server.py     # then open http://localhost:3000
```

**Command line:**

```sh
cd engine && python piece.py ../pieces/examples/night_transit.yaml
```

Scores need [LilyPond](https://lilypond.org) on the path; page images in the browser also need `pdftoppm` (poppler).
Without them the app still writes MIDI.

## Repository

```
engine/            the composition engine (plain modules, no web code)
app/server.py      FastAPI server: JSON API and the static front end
app/schema.py      menu definitions for the front end
app/static/        HTML, CSS and JavaScript (no framework, no build step)
pieces/examples/   example piece scripts
docs/              contracts (piece script, parts document), deployment, roadmap, reference tables
tests/             engine, parts, API tests (pytest)
```

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest -q tests
```

GitHub Actions runs the tests on every push and a container smoke test (build the image, start it, generate a piece with
score and MIDI) when the image or code changes.

## Deployment

Coolify builds the `Dockerfile`. See [docs/deployment-coolify.md](docs/deployment-coolify.md).

## Evidence labels

Settings and rules are labelled in the code as MEASURED (from the corpus measurements, Experiments 37 and 38 and the
v0.5-v0.7 validations) or DESIGN (a choice not yet measured). The part generators in Stage 1 are DESIGN throughout.
