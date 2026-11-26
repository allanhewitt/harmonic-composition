"""Registry of sequencer engines: one instance of each machine, each switched on or off (on by default).

Each engine module provides ID, NAME, DEFAULTS and generate(ctx, settings) -> part. New engines are added to
ENGINES in the handoff's order as they are built.
"""
import copy
import seqcore as S
import seq960

ENGINES = [seq960]          # Euclidean, Polymetric, TB-303, Turing, Metropolix, Marbles, Rene, Nodal to follow


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
