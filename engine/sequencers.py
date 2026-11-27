"""Registry of sequencer engines: one instance of each machine, each switched on or off (on by default).

Each engine module provides ID, NAME, DEFAULTS and generate(ctx, settings) -> part. Engines are listed in the
handoff's order; the TR-808 belongs to the drum family. Seq Drift comes last and is off by default (it needs slow harmony).
"""
import copy
import seqcore as S
import seq960
import seqengines as E
import seqdrift

ENGINES = [seq960] + E.ENGINES + [seqdrift.Drift]   # 960, Euclidean, Polymetric, TB-303, Turing, Metropolix, Marbles, René, Nodal, Drift


def defaults():
    return {e.ID: copy.deepcopy(e.DEFAULTS) for e in ENGINES}


def generate(doc, result, plan, settings=None):
    """Parts for every enabled engine."""
    settings = settings or {}
    unknown = set(settings) - {e.ID for e in ENGINES}
    if unknown:
        raise ValueError(f"Unknown sequencer(s): {', '.join(sorted(unknown))}. Available: {', '.join(e.ID for e in ENGINES)}.")
    ctx = S.Context(doc, result, plan)
    parts = []
    for e in ENGINES:
        cfg = dict(copy.deepcopy(e.DEFAULTS), **settings.get(e.ID, {}))
        if cfg.get('enabled', True):
            parts.append(e.generate(ctx, cfg))
    return parts
