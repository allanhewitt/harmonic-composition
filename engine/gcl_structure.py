"""Structure stage of the Harmonic Composition generator: song parameters (CTX01) and form (CTX02).

Taken unchanged from GCL Version One v0.3 (CTX00 engine cell). Its context document
(schema gcl-context-0.1) is the input to the harmonic engine. The form models and the
recurrence, contrast and symmetry controls are DESIGN heuristics, not fitted models.
"""
from dataclasses import dataclass, asdict
import random, hashlib, json, re, copy, shlex
from functools import lru_cache

MODELS = ['verse_chorus','aaba','cyclic','through_composed','evolving','arch','modular','auto','explicit']
GLOBAL_DEFAULTS = dict(composition='Morning Sketch',tempo='100',meter='4/4',key='C major',length='128',seed='42')
STRUCT_DEFAULTS = dict(model='verse_chorus',sections='5..9',section_length='8..24',phrase_length='4..8',intro=True,bridge=True,outro=True,recurrence=70,contrast=40,symmetry=60,explicit='intro 8\nverse 24\nchorus 16\nverse 24\nchorus 16\nbridge 16\nchorus 16\noutro 8')

def rng_for(seed,stage,variant=0):
    return random.Random(int.from_bytes(hashlib.sha256(f'{seed}:{stage}:{variant}'.encode()).digest()[:8],'big'))

def span(value,lo,hi,auto=None):
    s=str(value).strip().lower().removesuffix(' bars').strip()
    if s=='auto' and auto is not None: return auto
    m=re.fullmatch(r'(\d+)(?:\.\.(\d+))?',s)
    if not m: raise ValueError(f'Expected integer or range, got {value!r}')
    a=int(m[1]); b=int(m[2] or a)
    if not lo<=a<=b<=hi: raise ValueError(f'{value!r} must lie within {lo}..{hi}')
    return a,b

def resolve_global(cfg,variant=0,auto_seed=None):
    seed_text=str(cfg['seed']).strip().lower()
    if seed_text=='auto': seed=auto_seed if auto_seed is not None else random.SystemRandom().randrange(2**32)
    else:
        seed=int(seed_text)
        if not 0<=seed<2**63: raise ValueError('Seed must be 0..2^63−1 or auto.')
    r=rng_for(seed,'global',variant)
    tempo=r.randint(*span(cfg['tempo'],20,300,(80,130)))
    length=r.randint(*span(cfg['length'],1,1024,(64,128)))
    meter=str(cfg['meter']).strip(); m=re.fullmatch(r'(\d+)/(1|2|4|8|16)',meter)
    if not m or not 1<=int(m[1])<=32: raise ValueError('Meter must be a time signature such as 4/4 or 6/8.')
    key=str(cfg['key']).strip()
    if key.lower()=='auto': key=r.choice('C Db D Eb E F F# G Ab A Bb B'.split())+' '+r.choice(['major','minor'])
    if not re.fullmatch(r'[A-G][#b]? (major|minor|dorian|phrygian|lydian|mixolydian|locrian)',key): raise ValueError('Key must be root + mode, e.g. D major, or auto.')
    return dict(composition=str(cfg['composition']).strip() or 'Untitled',tempo=tempo,meter=meter,key=key,length=length,seed=seed,variant=variant)

def allowed_ints(value,lo,hi):
    s=str(value).strip().lower().removesuffix(' bars').strip()
    if ',' not in s:
        a,b=span(s,lo,hi); return list(range(a,b+1))
    parts=s.split(',')
    if any(not re.fullmatch(r'\d+',x.strip()) for x in parts): raise ValueError('Use integer choices separated by commas.')
    vals=sorted(set(int(x) for x in parts))
    if not vals or min(vals)<lo or max(vals)>hi: raise ValueError(f'Choices must be within {lo}..{hi}.')
    return vals

@lru_cache(None)
def discrete_phrase_counts(n,choices):
    if n==0: return (0,)
    if n<0: return ()
    # iterative DP avoids Python recursion limits for long sections
    reachable=[{0}]+[set() for _ in range(n)]
    for i in range(1,n+1):
        for x in choices:
            if x<=i: reachable[i].update(k+1 for k in reachable[i-x])
    return tuple(sorted(reachable[n]))

def make_phrase_choices(n,choices,r,symmetry):
    if choices==list(range(min(choices),max(choices)+1)): return make_phrases(n,min(choices),max(choices),r,symmetry)
    opts=discrete_phrase_counts(n,tuple(choices))
    if not opts: raise ValueError(f'{n} bars cannot be subdivided using {choices}.')
    k=r.choice(opts); rem=n; out=[]
    while k:
        legal=[x for x in choices if x<=rem and k-1 in discrete_phrase_counts(rem-x,tuple(choices))]
        x=min(legal,key=lambda x:abs(x-rem/k)) if r.random()<symmetry/100 else r.choice(legal)
        out.append(x); rem-=x; k-=1
    return out

def parse_rows(s):
    rows=[]
    for ln in s.splitlines():
        if not ln.strip(): continue
        m=re.fullmatch(r'([A-Za-z][A-Za-z0-9_\-]*)\s+(\d+)',ln.strip())
        if not m: raise ValueError(f'Expected section_name bars; got {ln!r}')
        rows.append((m[1],int(m[2])))
    if not rows: raise ValueError('Enter at least one section.')
    return rows

def phrase_options(n,lo,hi):
    return [k for k in range(1,n+1) if k*lo<=n<=k*hi]

def make_phrases(n,lo,hi,r,symmetry):
    ks=phrase_options(n,lo,hi)
    if not ks: raise ValueError(f'{n} bars cannot be subdivided into phrases of {lo}..{hi} bars.')
    k=r.choice(ks); rem=n; out=[]
    for i in range(k):
        low=max(lo,rem-(k-i-1)*hi); high=min(hi,rem-(k-i-1)*lo)
        x=min(high,max(low,round(rem/(k-i)))) if r.random()<symmetry/100 else r.randint(low,high)
        out.append(x); rem-=x
    return out

def model_forms(cfg,r,total,allowed):
    model=cfg['model']; min_l=min(allowed); max_l=max(allowed)
    if model=='verse_chorus':
        core=['verse','chorus','verse','chorus']
        if cfg['bridge']: core+=['bridge','chorus']
        elif cfg['recurrence']>=70: core+=['chorus']
        return [(['intro'] if cfg['intro'] else [])+core+(['outro'] if cfg['outro'] else [])]
    if model=='aaba': return [['A','A','B','A']]
    if model=='arch': return [['A','B','C','B','A'],['A','B','C','D','C','B','A']]
    low,high=span(cfg['sections'],1,64,(5,9))
    counts=[k for k in range(low,high+1) if k*min_l<=total<=k*max_l]; r.shuffle(counts)
    forms=[]
    for k in counts:
        if model=='cyclic': names=[['A','B'][i%2] for i in range(k)]
        elif model=='through_composed': names=[f'S{i+1}' for i in range(k)]
        elif model=='evolving': names=['A' if i==0 else f'A_v{i}' for i in range(k)]
        else:
            names=['A']; pool=['A']
            for i in range(1,k):
                if r.random()<cfg['recurrence']/100:
                    opts=[v for v in pool if v!=names[-1]]
                    names.append(r.choice(opts) if opts and r.random()<cfg['contrast']/100 else r.choice(pool))
                else:
                    name=f'S{len(pool)+1}'; pool.append(name); names.append(name)
        forms.append(names)
    return forms

def assemble(names,lengths,cfg,r,locked=None):
    pc=allowed_ints(cfg['phrase_length'],1,128); out=[]; start=0; seen={}; locked=locked or {}
    for i,(name,n) in enumerate(zip(names,lengths)):
        seen[name]=seen.get(name,0)+1
        phrases=copy.deepcopy(locked[i]['phrases']) if i in locked else make_phrase_choices(n,pc,r,cfg['symmetry'])
        out.append(dict(index=i,identity=name,occurrence=seen[name],start=start,bars=n,phrases=phrases))
        start+=n
    return out

def validate_structure(rows,g,cfg,locked=None):
    if not rows: raise ValueError('No sections.')
    pc=allowed_ints(cfg['phrase_length'],1,128); sl=allowed_ints(cfg['section_length'],1,1024)
    pos=0; seen={}
    for i,s in enumerate(rows):
        name=s['identity']; n=s['bars']; seen[name]=seen.get(name,0)+1
        if s['index']!=i or s['start']!=pos or s['occurrence']!=seen[name]: raise ValueError('Section indexing or start is inconsistent.')
        if n<=0 or (cfg['model']!='explicit' and n not in sl): raise ValueError(f'{name}: invalid section length {n}.')
        if not s['phrases'] or sum(s['phrases'])!=n or any(p not in pc for p in s['phrases']): raise ValueError(f'{name}: invalid phrase subdivision.')
        pos+=n
    if pos!=g['length']: raise ValueError(f'Structure is {pos} bars; expected {g["length"]}.')
    if locked:
        for i,s in locked.items():
            if i>=len(rows) or any(rows[i][k]!=s[k] for k in ['identity','occurrence','start','bars','phrases']): raise ValueError(f'Locked section {i+1} would change. Unlock it first.')
    return True

def generate_structure(g,cfg,variant=0,locked=None,previous=None):
    locked=locked or {}; r=rng_for(g['seed'],'structure',variant)
    if cfg['model'] not in MODELS: raise ValueError('Unknown model.')
    for k in ['recurrence','contrast','symmetry']:
        if not 0<=int(cfg[k])<=100: raise ValueError(f'{k} must be 0..100.')
    sl=allowed_ints(cfg['section_length'],1,1024); pc=allowed_ints(cfg['phrase_length'],1,128)
    allowed=[n for n in sl if (phrase_options(n,min(pc),max(pc)) if pc==list(range(min(pc),max(pc)+1)) else discrete_phrase_counts(n,tuple(pc)))]
    if cfg['model']=='explicit':
        pairs=parse_rows(cfg['explicit']); names,ls=zip(*pairs)
        rows=assemble(names,ls,cfg,r,locked); validate_structure(rows,g,cfg,locked); return rows
    if not allowed: raise ValueError('No section lengths can satisfy the phrase range.')
    forms=model_forms(cfg,r,g['length'],allowed)
    if locked:
        if previous is None: raise ValueError('Locks require a previous candidate.')
        forms=[f for f in forms if len(f)==len(previous) and all(f[i]==s['identity'] for i,s in locked.items())]
        # For stochastic forms, preserve the existing identity sequence while locks exist.
        if cfg['model'] in ('auto','modular') and not forms: forms=[[s['identity'] for s in previous]]
    for names in forms:
        k=len(names); total=g['length']
        @lru_cache(None)
        def feasible(i,pos):
            if i==k: return pos==total
            rem=k-i
            if not rem*min(allowed)<=total-pos<=rem*max(allowed): return False
            if i in locked:
                s=locked[i]; choices=[s['bars']] if pos==s['start'] and s['bars'] in allowed else []
            else: choices=allowed
            return any(feasible(i+1,pos+x) for x in choices if pos+x<=total)
        if not feasible(0,0): continue
        pos=0; lengths=[]; prior={}
        for i,name in enumerate(names):
            choices=[locked[i]['bars']] if i in locked else [x for x in allowed if feasible(i+1,pos+x)]
            target=prior.get(name,(total-pos)/(k-i))
            if name in ('intro','outro'): target=min(target,8)
            weights=[1/(1+abs(x-target))**(cfg['symmetry']/35) for x in choices]
            n=r.choices(choices,weights=weights,k=1)[0]; lengths.append(n); pos+=n; prior[name]=n
        rows=assemble(names,lengths,cfg,r,locked)
        try: validate_structure(rows,g,cfg,locked); return rows
        except ValueError: continue
    raise ValueError('No feasible form for this model, length, phrase/section constraints and locks. Adjust constraints or unlock sections.')

def edit_structure(text,g,cfg,variant,previous,locked):
    names,ls=zip(*parse_rows(text)); r=rng_for(g['seed'],'edit',variant)
    rows=assemble(names,ls,cfg,r,locked)
    for i,s in enumerate(rows):
        if i<len(previous) and s['identity']==previous[i]['identity'] and s['bars']==previous[i]['bars']:
            s['phrases']=copy.deepcopy(previous[i]['phrases'])
    validate_structure(rows,g,cfg,locked); return rows

def gcl_script(gc,sc):
    lines=[f'composition {json.dumps(gc["composition"],ensure_ascii=False)}']+[f'{k} {gc[k]}' for k in ['tempo','meter','key','length','seed']]+['','structure']
    for k in ['model','sections','section_length','phrase_length','intro','bridge','outro','recurrence','contrast','symmetry']:
        if sc['model']=='explicit' and k not in ('model','phrase_length','symmetry'): continue
        v=sc[k]; lines.append(f'    {k} {str(v).lower() if isinstance(v,bool) else v}')
    if sc['model']=='explicit': lines.extend('    section '+s for s in sc['explicit'].splitlines() if s.strip())
    return '\n'.join(lines+['end','generate structure'])

def parse_gcl(text):
    gc=copy.deepcopy(GLOBAL_DEFAULTS); sc=copy.deepcopy(STRUCT_DEFAULTS); inside=False; explicit=[]
    for ln in text.splitlines():
        ln=ln.strip()
        if not ln or ln.startswith('#'): continue
        if ln=='structure' and not inside: inside=True; continue
        if ln=='end' and inside: inside=False; continue
        if ln=='generate structure' and not inside: continue
        parts=ln.split(maxsplit=1)
        if len(parts)!=2: raise ValueError(f'Invalid instruction: {ln}')
        k,v=parts
        if inside:
            if k=='section': explicit.append(v)
            elif sc['model']=='explicit' and re.fullmatch(r'\d+',v) and k not in ('symmetry','phrase_length'): explicit.append(ln)
            elif k in sc and k!='explicit':
                if isinstance(sc[k],bool):
                    if v not in ('true','false'): raise ValueError(f'{k}: use true or false.')
                    sc[k]=v=='true'
                elif isinstance(sc[k],int): sc[k]=int(v)
                else: sc[k]=v
            else: explicit.append(ln)
        elif k in gc: gc[k]=json.loads(v) if k=='composition' and v.startswith('"') else v
        else: raise ValueError(f'Unknown global parameter: {k}')
    if inside: raise ValueError('Missing end for structure block.')
    if explicit:
        if sc['model']!='explicit': raise ValueError('Explicit section rows require model explicit.')
        sc['explicit']='\n'.join(explicit); parse_rows(sc['explicit'])
    return gc,sc

class Worksheet:
    def __init__(self):
        self.harm_candidate=None; self.harm_accepted=None; self.harm_parent=None; self.harm_accepted_parent=None; self.harm_config=None; self.harm_accepted_config=None; self.harm_variant=-1; self.harm_locks=[]
        self.global_candidate=None; self.global_accepted=None; self.structure_candidate=None; self.structure_accepted=None
        self.structure_config=None; self.accepted_structure_config=None; self.global_revision=0; self.structure_revision=0
        self.candidate_parent=None; self.accepted_parent=None; self.global_variant=-1; self.structure_variant=-1; self.locks={}
    def generate_global(self,cfg):
        v=self.global_variant+1; result=resolve_global(cfg,v); self.global_variant=v; self.global_candidate=result; return result
    def accept_global(self):
        if self.global_candidate is None: raise ValueError('Generate global parameters first.')
        if self.global_accepted!=self.global_candidate:
            self.global_revision+=1; self.global_accepted=copy.deepcopy(self.global_candidate); self.locks={}
    def generate_form(self,cfg):
        if self.global_accepted is None: raise ValueError('Accept global parameters first.')
        v=self.structure_variant+1
        result=generate_structure(self.global_accepted,cfg,v,self.locks,self.structure_candidate)
        self.structure_candidate=result; self.structure_config=copy.deepcopy(cfg); self.candidate_parent=self.global_revision; self.structure_variant=v; return result
    def accept_form(self):
        if self.structure_candidate is None or self.candidate_parent!=self.global_revision: raise ValueError('Generate a structure using current accepted global parameters first.')
        validate_structure(self.structure_candidate,self.global_accepted,self.structure_config,self.locks)
        if self.structure_accepted!=self.structure_candidate or self.accepted_parent!=self.global_revision:
            self.structure_revision+=1; self.structure_accepted=copy.deepcopy(self.structure_candidate); self.accepted_parent=self.global_revision; self.accepted_structure_config=copy.deepcopy(self.structure_config)
    def context(self):
        if self.structure_accepted is None or self.accepted_parent!=self.global_revision: return None
        return dict(schema='gcl-context-0.1',global_parameters=copy.deepcopy(self.global_accepted),sections=copy.deepcopy(self.structure_accepted),structure_revision=self.structure_revision)
    def harmony_context(self):
        ctx=self.context()
        if ctx is None or self.harm_accepted is None or self.harm_accepted_parent!=self.structure_revision: return None
        return dict(ctx,harmony=copy.deepcopy(self.harm_accepted),harmony_config=copy.deepcopy(self.harm_accepted_config))
    def snapshot(self): return copy.deepcopy(self.__dict__)
    @classmethod
    def restore(cls,data):
        x=cls(); x.__dict__.update(copy.deepcopy(data)); x.locks={int(k):v for k,v in x.locks.items()}
        if x.global_accepted is not None and x.candidate_parent==x.global_revision and x.structure_candidate is not None: validate_structure(x.structure_candidate,x.global_accepted,x.structure_config,x.locks)
        if x.context(): validate_structure(x.structure_accepted,x.global_accepted,x.accepted_structure_config)
        return x
