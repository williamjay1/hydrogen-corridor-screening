"""Common-input hydrogen corridor bounds. All results are annual planning bounds."""
from pathlib import Path
from collections import defaultdict, deque
import itertools, json, hashlib, time
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

P=Path(__file__).resolve().parents[1]; ROOT=P
RAW=Path(__import__('os').environ.get('PROJECT16_RAW_DIR', str(P/'external_raw'))); D=P/'data'; R=P/'runs'; A=P/'audits'
for x in (D,R,A): x.mkdir(exist_ok=True)
EU={'Austria','Belgium','Bulgaria','Croatia','Cyprus','Czechia','Denmark','Estonia','Finland','France','Germany','Greece','Hungary','Ireland','Italy','Latvia','Lithuania','Luxembourg','Malta','Netherlands','Poland','Portugal','Romania','Slovakia','Slovenia','Spain','Sweden'}
IND={'Refining','Industrial heat','Ammonia','Other chemicals','Methanol','Steel'}

def js(path,obj): path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
def csv(df,name): df.to_csv(R/name,index=False)

def prepare_from_raw():
    files=[RAW/'tyndp/TYNDP_2024_Annex_A_List_of_projects.xlsx',RAW/'tyndp/TYNDP_2024_Annex_C2_Hydrogen_Infrastructure_Capacities.xlsx',RAW/'eho/Hydrogen_demand_2024_Update_2025.xlsx',RAW/'eho/Hydrogen_demand_forecasts_2023.xlsx']
    manifest=[dict(file=f.name,sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in files]
    js(A/'raw_file_integrity.json',manifest)
    e=pd.read_csv(D/'network_edges.csv')
    raw=pd.read_excel(files[1],sheet_name='Annex C2_Detailed_Nodes')
    checks=[]
    for _,r in e.iterrows():
        s=raw.iloc[int(r.source_row)-2]
        ok=all(str(r[k]).strip()==str(s[v]).strip() for k,v in [('from_node','From Node'),('to_node','To Node')]) and int(r.year)==int(s.Year)
        for k,v in [('capacity_pci_pmi_gwh_per_day','PCI/PMI'),('capacity_advanced_gwh_per_day','ADVANCED')]:
            value=pd.to_numeric(s[v],errors='coerce'); value=0 if pd.isna(value) else float(value)
            ok &= abs(float(r[k])-value)<1e-8
        checks.append(dict(edge_id=r.edge_id,excel_row=int(r.source_row),pass_check=bool(ok)))
    assert all(r['pass_check'] for r in checks)
    pd.DataFrame(checks).to_csv(A/'raw_edge_cell_checks.csv',index=False)
    e.to_csv(D/'network_edges.csv',index=False)
    c=pd.read_csv(D/'carrier_project_evidence.csv')
    rawc=pd.read_excel(files[0],sheet_name='H2L',header=3)
    audit=[]
    for i,r in c.iterrows():
        found=rawc[rawc.Code.eq(r.project_code) & pd.to_numeric(rawc['Commissioning Year'],errors='coerce').eq(r.commissioning_year) & rawc['Importing Hydrogen Carrier'].eq(r.reported_carrier)]
        assert len(found)==1,(r.project_code,len(found))
        s=found.iloc[0]; value=float(s['Hydrogen Import Capacity (GWh/d)'])
        assert abs(value-r.reported_capacity_gwh_per_day)<1e-8
        c.loc[i,'excel_row']=int(found.index[0])+5
        c.loc[i,'conversion_efficiency_pct']=pd.to_numeric(s['Average efficiency of  the conversion to hydrogen (%)'],errors='coerce')
        audit.append(dict(project_code=r.project_code,year=int(r.commissioning_year),excel_row=int(found.index[0])+5,capacity_gwh_per_day=value,pass_check=True))
    c.to_csv(D/'carrier_project_evidence.csv',index=False)
    pd.DataFrame(audit).to_csv(A/'raw_carrier_cell_checks.csv',index=False)
    candidates=pd.read_csv(D/'candidates.csv')
    candidates.to_csv(D/'candidates.csv',index=False)
    agg=pd.read_excel(files[2],sheet_name='Annual consumption aggregated',header=6)
    agg['Country']=agg.Country.replace({'Luxemburg':'Luxembourg'})
    agg['Total consumption']=pd.to_numeric(agg['Total consumption'],errors='coerce').fillna(0)
    industrial=agg[agg['End-use'].isin(IND)].copy()
    denom=industrial['Total consumption'].sum()
    country=industrial[industrial.Country.isin(EU)].groupby('Country')['Total consumption'].sum().rename('industrial_h2_tonnes_2024').reset_index()
    country['allocation_weight_of_eho_europe']=country.industrial_h2_tonnes_2024/denom
    country=country[country.industrial_h2_tonnes_2024>0].copy()
    country.to_csv(D/'country_demand_weights.csv',index=False)
    f=pd.read_excel(files[3],header=6); f=f.rename(columns={'Industry':'industry_twh'})
    scenarios=[]
    for year,level,q in itertools.product((2030,2040),('PCI/PMI','Advanced'),(.25,.5,.75)):
        value=pd.to_numeric(f.loc[f.Year.eq(year),'industry_twh'],errors='coerce').quantile(q)
        scenarios.append(dict(scenario_id=f'{year}_{level.replace("/","")}_{q}',year=year,level=level,quantile=q,eho_industry_twh=float(value),eu_coverage_weight=float(country.allocation_weight_of_eho_europe.sum())))
    pd.DataFrame(scenarios).to_csv(D/'scenarios.csv',index=False)
    return e,c,candidates,country,scenarios


def prepare():
    """Load the archived derived inputs; no network or author-specific path required."""
    return (pd.read_csv(D/'network_edges.csv',float_precision='round_trip'),pd.read_csv(D/'carrier_project_evidence.csv',float_precision='round_trip'),
            pd.read_csv(D/'candidates.csv'),pd.read_csv(D/'country_demand_weights.csv',float_precision='round_trip'),
            pd.read_csv(D/'scenarios.csv',float_precision='round_trip').to_dict('records'))

class Screen:
    def __init__(self,e,c,candidates,dem,scenarios):
        self.e=e;self.c=c;self.candidates=candidates;self.dem=dem;self.scenarios=scenarios
        self.keys=tuple(candidates.terminal_node)
        self.country=dict(zip(candidates.terminal_node,candidates.country))
        self.groups={co:list(g.terminal_node) for co,g in candidates.groupby('country')}
        self.mapping_cases=[dict(zip(self.groups,choice)) for choice in itertools.product(*self.groups.values())]
        self._cache={}

    def build(self,s,selected=None,share=.2,mode='graph',mapping=None,phase='latest',maturity='all',scale=1.,conversion=False):
        key=(s['scenario_id'],share,mode,json.dumps(mapping,sort_keys=True),phase,maturity,scale,conversion)
        if key not in self._cache:
            self._cache[key]=self._build_uncached(s,None,share,mode,mapping,phase,maturity,scale,conversion)
        arcs,demand=self._cache[key]
        if selected is None:return arcs,demand
        selected=set(selected)
        arcs=[a for a in arcs if not ((a[3]=='terminal_backbone' and a[0] not in selected) or (a[3] in ('pool_assignment','pool_duplicated') and a[1] not in selected))]
        return arcs,demand

    def _build_uncached(self,s,selected=None,share=.2,mode='graph',mapping=None,phase='latest',maturity='all',scale=1.,conversion=False):
        selected=set(self.keys if selected is None else selected)
        demand={r.Country:s['eho_industry_twh']*1000*share*r.allocation_weight_of_eho_europe for _,r in self.dem.iterrows()}
        big=sum(demand.values())*2+1
        e=self.e[self.e.year.eq(s['year'])].copy()
        capcol='capacity_pci_pmi_gwh_per_day' if s['level']=='PCI/PMI' else 'capacity_advanced_gwh_per_day'
        c=self.c[self.c.commissioning_year.le(s['year'])].copy()
        if maturity=='advanced':c=c[c.maturity_status.eq('Advanced')]
        if phase=='latest':
            c=c.sort_values('commissioning_year').drop_duplicates(['project_code','carrier_class'],keep='last')
        c['cap']=c.reported_capacity_gwh_per_day*365*scale
        if conversion:
            # Literal disclosed efficiencies only; missing values left at listed H2-equivalent capacity.
            c['cap']*=c.conversion_efficiency_pct.fillna(100).clip(0,100)/100
        pools=c.groupby('country').cap.sum().to_dict()
        arcs=[]
        def add(u,v,cap,kind,ref=''):
            if cap>1e-10: arcs.append((u,v,float(cap),kind,ref))
        for co,ts in self.groups.items():
            pool=pools.get(co,0)
            if mode=='duplicated_pool':
                for t in ts:
                    if t in selected:add('SOURCE',t,pool,'pool_duplicated')
            else:
                add('SOURCE','POOL:'+co,pool,'carrier_pool',co)
                for t in ts:
                    if t in selected and (mapping is None or mapping[co]==t):add('POOL:'+co,t,big,'pool_assignment')
        nodeco={}
        for _,r in e.iterrows():
            if r.edge_type=='backbone':nodeco[r.from_node]=r.from_country
            nodeco[r.to_node]=r.to_country
            if r.edge_type=='terminal_backbone' and r.from_node not in selected:continue
            add(r.from_node,r.to_node,float(r[capcol])*365*scale,r.edge_type,r.edge_id)
        if mode=='topology_free':
            arcs=[a for a in arcs if a[3]!='backbone']
            receivers=set(e.loc[e.edge_type.eq('terminal_backbone'),'to_node'])
            for n in receivers:
                for co in demand:add(n,'DEMAND:'+co,big,'topology_relaxation')
        else:
            for n,co in nodeco.items():
                if co in demand:add(n,'DEMAND:'+co,big,'country_accounting')
        for co,v in demand.items():add('DEMAND:'+co,'SINK',v,'demand',co)
        return arcs,demand

def maxflow(arcs):
    """Edmonds--Karp with separate residual reverse arcs; capacities in GWh/year."""
    nodes=sorted({a[0] for a in arcs}|{a[1] for a in arcs}|{'SOURCE','SINK'}); ids={n:i for i,n in enumerate(nodes)}
    adj=[[] for _ in nodes]; orig=[]
    for u,v,cap,kind,ref in arcs:
        u,v=ids[u],ids[v];i=len(adj[u]);j=len(adj[v]);adj[u].append([v,j,cap]);adj[v].append([u,i,0.]);orig.append((u,i,cap))
    source,sink=ids['SOURCE'],ids['SINK']; value=0.
    while True:
        prev=[None]*len(nodes);prev[source]=(-1,-1);q=deque([source])
        while q and prev[sink] is None:
            u=q.popleft()
            for j,(v,rev,cap) in enumerate(adj[u]):
                if cap>1e-8 and prev[v] is None:prev[v]=(u,j);q.append(v)
        if prev[sink] is None:break
        v=sink;delta=float('inf')
        while v!=source:u,j=prev[v];delta=min(delta,adj[u][j][2]);v=u
        v=sink
        while v!=source:u,j=prev[v];rev=adj[u][j][1];adj[u][j][2]-=delta;adj[v][rev][2]+=delta;v=u
        value+=delta
    reach={i for i,p in enumerate(prev) if p is not None}
    cuts=[a for a in arcs if ids[a[0]] in reach and ids[a[1]] not in reach]
    flows=[cap-adj[u][i][2] for u,i,cap in orig]
    assert abs(value-sum(a[2] for a in cuts))<1e-5
    return value,flows,cuts

def lp(arcs):
    nodes=sorted(({a[0] for a in arcs}|{a[1] for a in arcs})-{'SOURCE','SINK'});idx={n:i for i,n in enumerate(nodes)}
    mat=lil_matrix((len(nodes),len(arcs)));obj=np.zeros(len(arcs))
    for j,(u,v,cap,*_) in enumerate(arcs):
        if u in idx:mat[idx[u],j]-=1
        if v in idx:mat[idx[v],j]+=1
        if v=='SINK':obj[j]=-1
    res=linprog(obj,A_eq=mat.tocsr(),b_eq=np.zeros(len(nodes)),bounds=[(0,a[2]) for a in arcs],method='highs')
    assert res.success,res.message
    return -res.fun

def evaluate(model,selected=None,**kwargs):
    out=[]
    for s in model.scenarios:
        arcs,d=model.build(s,selected,**kwargs);v,_,_=maxflow(arcs);total=sum(d.values())
        out.append((v,total,100*(1-v/total)))
    return out

def main():
    start=time.time();model=Screen(*prepare()); rows=[]; cutrows=[];flowrows=[];checks=[]
    configs=[('graph',{}),('topology_free',{'mode':'topology_free'}),('duplicated_pool',{'mode':'duplicated_pool'}),('additive_phases',{'phase':'additive'}),('advanced_carriers',{'maturity':'advanced'}),('conversion_adjusted',{'conversion':True})]
    for share in (.1,.2,.3,1.):
        for s in model.scenarios:
            for name,kw in configs:
                arcs,d=model.build(s,share=share,**kw);v,flows,cuts=maxflow(arcs);total=sum(d.values())
                rows.append({**s,'import_share':share,'configuration':name,'served_gwh':v,'target_gwh':total,'unmet_pct':100*(1-v/total)})
                if share==.2 and name=='graph':
                    val=lp(arcs);checks.append(dict(scenario_id=s['scenario_id'],maxflow=v,lp=val,abs_difference=abs(v-val),mincut=sum(a[2] for a in cuts)))
                    assert abs(val-v)<1e-5
                    for arc,f in zip(arcs,flows):
                        if f>1e-7:flowrows.append(dict(scenario_id=s['scenario_id'],from_node=arc[0],to_node=arc[1],capacity_gwh=arc[2],flow_gwh=f,kind=arc[3],source_ref=arc[4]))
                    for u,t,cap,kind,ref in cuts:cutrows.append(dict(scenario_id=s['scenario_id'],from_node=u,to_node=t,capacity_gwh=cap,kind=kind,source_ref=ref))
    csv(pd.DataFrame(rows),'scenario_results.csv');csv(pd.DataFrame(flowrows),'flows.csv');csv(pd.DataFrame(cutrows),'minimum_cuts.csv')
    pd.DataFrame(checks).to_csv(A/'independent_lp_checks.csv',index=False)
    # Census of every subset: topology, capacity and country demand held identical.
    portfolios=[]
    central=next(i for i,s in enumerate(model.scenarios) if s['year']==2040 and s['level']=='Advanced' and s['quantile']==.5)
    for k in range(1,len(model.keys)+1):
        for sel in itertools.combinations(model.keys,k):
            ev=evaluate(model,sel)
            portfolios.append(dict(budget=k,selection=';'.join(sel),worst_unmet_pct=max(x[2] for x in ev),central_unmet_pct=ev[central][2],sum_unmet_gwh=sum(x[1]-x[0] for x in ev)))
        print('subset budget',k,flush=True)
    census=pd.DataFrame(portfolios);csv(census,'all_subset_census.csv')
    four=census[census.budget.eq(4)].sort_values(['worst_unmet_pct','sum_unmet_gwh','selection']);best=set(four.iloc[0].selection.split(';'))
    det=set(four.sort_values(['central_unmet_pct','sum_unmet_gwh','selection']).iloc[0].selection.split(';'))
    # Capacity ranking uses central C2 terminal capacities only; ties alphabetical.
    col='capacity_advanced_gwh_per_day';e=model.e[model.e.year.eq(2040)&model.e.edge_type.eq('terminal_backbone')]
    capsel=set(e[e.from_node.isin(model.keys)].sort_values([col,'from_node'],ascending=[False,True]).head(4).from_node)
    greedy=set()
    for k in range(4):
        opts=[]
        for key in model.keys:
            if key in greedy:continue
            ev=evaluate(model,greedy|{key});opts.append((max(x[2] for x in ev),sum(x[1]-x[0] for x in ev),key))
        greedy.add(min(opts)[2])
    baselines=[]
    for name,sel in [('exact_minimax',best),('central_optimum',det),('capacity_rank',capsel),('greedy',greedy)]:
        ev=evaluate(model,sel);baselines.append(dict(method=name,selection=';'.join(sorted(sel)),worst_unmet_pct=max(x[2] for x in ev),sum_unmet_gwh=sum(x[1]-x[0] for x in ev)))
    csv(pd.DataFrame(baselines),'strong_baselines.csv')
    # All country-pool mass at one anonymous terminal per country: extreme allocations.
    # Zero C2 capacity stays zero, so evidence might be stranded. No probability is assigned.
    mappingrows=[]
    for _,row in census.iterrows():
        sel=set(row.selection.split(';')); values=[]
        for mi,mp in enumerate(model.mapping_cases):
            ev=evaluate(model,sel,mapping=mp);values.append(max(x[2] for x in ev))
        mappingrows.append(dict(budget=int(row.budget),selection=row.selection,optimistic_worst_unmet_pct=row.worst_unmet_pct,mapping_worst_unmet_pct=max(values),mapping_best_unmetmet_pct=min(values)))
    mapc=pd.DataFrame(mappingrows).sort_values(['mapping_worst_unmet_pct','optimistic_worst_unmet_pct','selection']);csv(mapc,'mapping_portfolio_census.csv')
    robust=set(mapc[mapc.budget.eq(4)].iloc[0].selection.split(';')); detailed=[]
    for name,sel in [('all_interfaces',set(model.keys)),('optimistic_selection',best),('mapping_robust_selection',robust)]:
        for mi,mp in enumerate(model.mapping_cases):
            for s,(v,total,u) in zip(model.scenarios,evaluate(model,sel,mapping=mp)):
                detailed.append(dict(method=name,mapping_id=mi,mapping=json.dumps(mp,sort_keys=True),scenario_id=s['scenario_id'],served_gwh=v,target_gwh=total,unmet_pct=u))
    csv(pd.DataFrame(detailed),'mapping_bounds.csv')
    outages=[]
    for name,sel in [('exact_minimax',best),('mapping_robust',robust)]:
        for fail in sorted(sel):
            ev=evaluate(model,sel-{fail});outages.append(dict(method=name,failed=fail,worst_unmet_pct=max(x[2] for x in ev)))
    csv(pd.DataFrame(outages),'outage_results.csv')
    sensitivity=[]
    for scale in (.5,.75,1.,1.25,1.5):
        ev=evaluate(model,best,scale=scale);sensitivity.append(dict(capacity_multiplier=scale,worst_unmet_pct=max(x[2] for x in ev)))
    csv(pd.DataFrame(sensitivity),'capacity_sensitivity.csv')
    summary=dict(country_count=len(model.dem),candidate_count=len(model.keys),edge_records=len(model.e),backbone_records=int(model.e.edge_type.eq('backbone').sum()),terminal_records=int(model.e.edge_type.eq('terminal_backbone').sum()),unique_directed_backbone_pairs=int(model.e.loc[model.e.edge_type.eq('backbone'),['from_node','to_node']].drop_duplicates().shape[0]),carrier_phase_records=len(model.c),unique_carrier_projects=int(model.c.project_code.nunique()),scenarios=len(model.scenarios),subset_count=len(census),four_portfolios=len(four),mapping_cases=len(model.mapping_cases),main_selection=sorted(best),mapping_selection=sorted(robust),baselines=baselines,elapsed_seconds=time.time()-start)
    js(R/'summary.json',summary);print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
