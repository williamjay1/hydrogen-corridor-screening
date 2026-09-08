from strengthen import *

model=Screen(*prepare());out=[]
for s in model.scenarios:
    base,d=model.build(s);groups=defaultdict(list)
    for u,v,cap,kind,ref in base:
        if kind=='country_accounting':groups[v].append(u)
    ambiguous={co:sorted(set(ns)) for co,ns in groups.items() if len(set(ns))>1}
    # Reduce equivalent choices by their actual incoming adjacency signature is not
    # necessary: enumerate every extreme assignment and preserve a witness.
    demand_choices=[dict(zip(ambiguous,opt)) for opt in itertools.product(*ambiguous.values())]
    worst=float('inf');witness=None;n=0
    for mid,mp in enumerate(model.mapping_cases):
        arcs,_=model.build(s,mapping=mp)
        fixed=[a for a in arcs if a[3]!='country_accounting' or a[1] not in ambiguous]
        account=[a for a in arcs if a[3]=='country_accounting' and a[1] in ambiguous]
        for aid,ass in enumerate(demand_choices):
            chosen=fixed+[a for a in account if a[0]==ass[a[1]]]
            value=maxflow(chosen)[0];n+=1
            if value<worst-1e-7:worst=value;witness=dict(source_mapping=mp,demand_mapping=ass)
    optimistic=maxflow(base)[0]
    out.append(dict(scenario_id=s['scenario_id'],joint_assignment_count=n,target_gwh=sum(d.values()),optimistic_served_gwh=optimistic,joint_lower_served_gwh=worst,joint_unmet_upper_pct=100*(1-worst/sum(d.values())),witness=json.dumps(witness,sort_keys=True)))
    print(s['scenario_id'],n,worst,flush=True)
csv(pd.DataFrame(out),'joint_assignment_bounds.csv')
