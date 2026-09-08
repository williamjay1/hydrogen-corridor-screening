from strengthen import *
import re

model=Screen(pd.read_csv(D/'network_edges.csv'),pd.read_csv(D/'carrier_project_evidence.csv'),pd.read_csv(D/'candidates.csv'),pd.read_csv(D/'country_demand_weights.csv'),pd.read_csv(D/'scenarios.csv').to_dict('records'))
rows=[]
for _,r in pd.read_csv(R/'joint_assignment_bounds.csv').iterrows():
    s=next(s for s in model.scenarios if s['scenario_id']==r.scenario_id)
    w=json.loads(r.witness);arcs,_=model.build(s,mapping=w['source_mapping'])
    chosen=[a for a in arcs if a[3]!='country_accounting' or a[1] not in w['demand_mapping'] or a[0]==w['demand_mapping'][a[1]]]
    value=lp(chosen);err=abs(value-r.joint_lower_served_gwh)
    assert err<1e-5,(r.scenario_id,err)
    rows.append(dict(case=r.scenario_id,type='joint minimum witness LP',abs_difference=err))
# Independent LP on seeded samples of distinct subset/source assignments.
rng=np.random.default_rng(160908)
for i in range(100):
    s=model.scenarios[int(rng.integers(12))];selected=[t for t in model.keys if rng.random()<.5]
    mp=model.mapping_cases[int(rng.integers(len(model.mapping_cases)))]
    arcs,_=model.build(s,selected=selected,mapping=mp,share=[.1,.2,.3,1.][i%4])
    err=abs(lp(arcs)-maxflow(arcs)[0]);assert err<1e-5
    rows.append(dict(case=str(i),type='seeded subset/source assignment LP',abs_difference=err))
pd.DataFrame(rows).to_csv(A/'additional_independent_lp_checks.csv',index=False)
print(json.dumps({'additional_LP_checks':len(rows),'maximum_LP_difference_GWh':max(r['abs_difference'] for r in rows)},indent=2))
