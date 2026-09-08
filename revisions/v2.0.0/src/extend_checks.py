from strengthen import *

def main():
    model=Screen(*prepare());checks=[]
    def check(name,condition,detail=''):
        checks.append(dict(check=name,passed=bool(condition),detail=str(detail)))
        assert condition,(name,detail)
    # Mechanism fixtures independently verify directedness, shared pools and the cut.
    fixture=[('SOURCE','P',8.,'pool',''),('P','A',8.,'assign',''),('P','B',8.,'assign',''),('A','D',5.,'edge',''),('B','D',5.,'edge',''),('D','SINK',20.,'demand','')]
    check('shared pool cannot duplicate supply',abs(maxflow(fixture)[0]-8)<1e-8)
    reverse=[('SOURCE','A',8.,'source',''),('B','A',8.,'edge',''),('B','SINK',8.,'demand','')]
    check('reverse edge not inferred',maxflow(reverse)[0]==0)
    c=pd.read_csv(R/'all_subset_census.csv');m=pd.read_csv(R/'mapping_portfolio_census.csv')
    four=c[c.budget.eq(4)];optim=float(four.worst_unmet_pct.min())
    ties=four[four.worst_unmet_pct.le(optim+1e-7)].copy()
    centralmin=float(four.central_unmet_pct.min());dt=four[four.central_unmet_pct.le(centralmin+1e-7)]
    summary=dict(optimistic_four_optima=len(ties),central_four_optima=len(dt),central_optimal_portfolios_worst_unmet_min=float(dt.worst_unmet_pct.min()),central_optimal_portfolios_worst_unmet_max=float(dt.worst_unmet_pct.max()),minimal_optimistic_budget=int(c.loc[c.worst_unmet_pct.le(optim+1e-7),'budget'].min()))
    csv(ties,'optimistic_optimal_portfolios.csv');csv(dt,'central_optimal_portfolios.csv')
    frontier=c.groupby('budget').worst_unmet_pct.min().to_frame('optimistic_unmet_pct').join(m.groupby('budget').mapping_worst_unmet_pct.min().rename('mapping_unmet_pct')).reset_index()
    csv(frontier,'budget_frontier.csv')
    check('budget monotonicity',all(np.diff(frontier.optimistic_unmet_pct)<=1e-7) and all(np.diff(frontier.mapping_unmet_pct)<=1e-7))
    check('mapping uncertainty cannot improve guarantee',all(frontier.mapping_unmet_pct>=frontier.optimistic_unmet_pct-1e-7))
    # Reconstruct national delivery balances and source/edge capacity bounds from saved flow.
    flows=pd.read_csv(R/'flows.csv')
    for sid,g in flows.groupby('scenario_id'):
        check('capacity '+sid,all(g.flow_gwh<=g.capacity_gwh+1e-6))
        bal=defaultdict(float)
        for _,r in g.iterrows():bal[r.from_node]-=r.flow_gwh;bal[r.to_node]+=r.flow_gwh
        check('conservation '+sid,max(abs(v) for n,v in bal.items() if n not in ('SOURCE','SINK'))<1e-5)
    # A conservative single-node demand assignment, shared across all carriers, checks
    # the otherwise unrestricted country accounting sink. Enumerate the choices in
    # countries with multiple C2 backbone nodes (France and Germany in this table).
    sinkrows=[]
    for s in model.scenarios:
        arcs,d=model.build(s);groups=defaultdict(list)
        for u,v,cap,kind,ref in arcs:
            if kind=='country_accounting':groups[v].append(u)
        ambiguous={co:sorted(set(nodes)) for co,nodes in groups.items() if len(set(nodes))>1}
        opts=list(itertools.product(*ambiguous.values()))
        vals=[]
        for opt in opts:
            assignment=dict(zip(ambiguous,opt));selected=[a for a in arcs if not (a[3]=='country_accounting' and a[1] in assignment and a[0]!=assignment[a[1]])]
            vals.append(maxflow(selected)[0])
        sinkrows.append(dict(scenario_id=s['scenario_id'],assignment_count=len(opts),optimistic_served_gwh=maxflow(arcs)[0],worst_single_node_served_gwh=min(vals),target_gwh=sum(d.values())))
    csv(pd.DataFrame(sinkrows),'country_sink_assignment_bounds.csv')
    # Cross-vintage stress: replace only matched project carrier records, explicitly
    # retain the 2024 network; unmatched projects stay frozen, not silently set to zero.
    new=pd.read_csv(D/'tyndp_2026_hydrogen_projects.csv')
    new.to_csv(D/'tyndp_2026_hydrogen_projects.csv',index=False)
    new['suffix']=new.code.str.extract(r'(\d+)$');vintage=[];changes=[]
    for code,g in model.c.groupby('project_code'):
        suffix=code.split('-')[-1];n=new[new.suffix.eq(suffix)].copy()
        n=n[n.importing_hydrogen_carrier_raw.astype(str).str.contains('ammon|amonia|lohc',case=False,regex=True)]
        if n.empty:vintage.extend(g.to_dict('records'));continue
        for _,r in n.iterrows():
            cap=pd.to_numeric(r.hydrogen_import_capacity_gwh_per_day,errors='coerce');year=pd.to_numeric(r.commissioning_year,errors='coerce')
            if pd.isna(cap) or pd.isna(year):continue
            a=g.iloc[0].to_dict();a.update(project_code=r.code,project_name=r.project_name,reported_capacity_gwh_per_day=float(cap),commissioning_year=float(year),maturity_status=r.maturity_status,conversion_efficiency_pct=pd.to_numeric(r.conversion_efficiency_pct,errors='coerce'))
            vintage.append(a);changes.append(dict(old_code=code,new_code=r.code,year=year,capacity=cap))
    updated=Screen(model.e,pd.DataFrame(vintage),model.candidates,model.dem,model.scenarios)
    rows=[]
    for share in (.2,1.):
        for s in model.scenarios:
            for label,mod in [('frozen_2024',model),('matched_2026_carriers_2024_network',updated)]:
                arcs,d=mod.build(s,share=share);value=maxflow(arcs)[0]
                rows.append(dict(scenario_id=s['scenario_id'],import_share=share,version=label,served_gwh=value,target_gwh=sum(d.values()),unmet_pct=100*(1-value/sum(d.values()))))
    csv(pd.DataFrame(rows),'cross_vintage_stress.csv');pd.DataFrame(changes).to_csv(A/'matched_vintage_replacements.csv',index=False)
    check('cross vintage matched projects',len(changes)>0)
    # Sample is determined before graph connectivity; countries not reached remain in denominator.
    check('fixed positive country sample',len(model.dem)==22 and all(model.dem.industrial_h2_tonnes_2024>0))
    check('raw edge audit',pd.read_csv(A/'raw_edge_cell_checks.csv').pass_check.all())
    check('raw carrier audit',pd.read_csv(A/'raw_carrier_cell_checks.csv').pass_check.all())
    # Source cut is a valid upper bound; it is not mislabeled as an independent transport model.
    results=pd.read_csv(R/'scenario_results.csv')
    for (sid,share),g in results.groupby(['scenario_id','import_share']):
        vals=dict(zip(g.configuration,g.served_gwh));check('topology upper bound '+sid+str(share),vals['topology_free']>=vals['graph']-1e-7)
    pd.DataFrame(checks).to_csv(A/'verification_checks.csv',index=False)
    summary['checks_passed']=len(checks);summary['all_checks_passed']=all(x['passed'] for x in checks)
    js(A/'extended_summary.json',summary);print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
