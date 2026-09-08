from strengthen import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.ticker import MaxNLocator

F=P/'figures';PRE=P/'previews';PRE.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.labelsize':11,'axes.titlesize':11,'xtick.labelsize':10,'ytick.labelsize':10,'legend.fontsize':10,'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,'lines.linewidth':1.8,'savefig.facecolor':'white'})
BLUE='#246A91';ORANGE='#C66B2B';GREEN='#2C8069';RED='#B4464B';GREY='#87949D'
model=Screen(*prepare());S=pd.read_csv(R/'scenario_results.csv');J=pd.read_csv(R/'joint_assignment_bounds.csv');M=pd.read_csv(R/'mapping_bounds.csv');C=pd.read_csv(R/'all_subset_census.csv');MP=pd.read_csv(R/'mapping_portfolio_census.csv');SUMMARY=json.loads((R/'summary.json').read_text());QA=[]
LABEL={'LH2_Tk_BE':'BE','LH2_Tk_DE':'DE','LH2_Tk_DEbp':'DEbp','LH2_Tk_FRn':'FRn','LH2_Tk_FRSW':'FRSW','LH2_Tk_FRW':'FRW','LH2_Tk_ITa':'ITa','LH2_Tk_NL':'NL','LH2_Tk_PLN':'PLN'}
ISO=dict(zip(['Austria','Belgium','Bulgaria','Croatia','Czechia','Denmark','Finland','France','Germany','Greece','Hungary','Ireland','Italy','Lithuania','Netherlands','Poland','Portugal','Romania','Slovakia','Slovenia','Spain','Sweden'],['AT','BE','BG','HR','CZ','DK','FI','FR','DE','GR','HU','IE','IT','LT','NL','PL','PT','RO','SK','SI','ES','SE']))
def save(fig,num):
    fig.canvas.draw()
    for ax in fig.axes:
        for axis,lim in [(ax.xaxis,ax.get_xlim()),(ax.yaxis,ax.get_ylim())]:
            lo,hi=sorted(lim)
            for tick in axis.get_major_ticks():
                if not lo-1e-7<=tick.get_loc()<=hi+1e-7:tick.label1.set_visible(False);tick.label2.set_visible(False)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();outside=[]
    for t in fig.findobj(matplotlib.text.Text):
        if t.get_visible() and t.get_text().strip():
            b=t.get_window_extent(renderer)
            if b.x0<-.5 or b.y0<-.5 or b.x1>fig.bbox.x1+.5 or b.y1>fig.bbox.y1+.5:outside.append(t.get_text())
    assert not outside,(num,outside)
    name=f'figure{num:02d}'
    fig.savefig(F/(name+'.pdf'))
    fig.savefig(F/(name+'.png'),dpi=900)
    fig.savefig(PRE/(name+'.png'),dpi=150)
    QA.append(dict(figure=name,outside_text=outside,figure_inches=fig.get_size_inches().tolist(),minimum_declared_font_pt=10))
    plt.close(fig);print('figure',num,flush=True)
def tidy(ax):ax.grid(axis='x',color='#E3E7EB',linewidth=.6);ax.set_axisbelow(True)

# 1. Reachability is derived from explicit edges, not hand-drawn geographic routes.
fig,axes=plt.subplots(2,1,figsize=(7.1,5.9),layout='constrained')
for ax,(year,level,panel) in zip(axes,[(2030,'PCI/PMI','a'),(2040,'Advanced','b')]):
    s=next(s for s in model.scenarios if s['year']==year and s['level']==level and s['quantile']==.5)
    arcs,d=model.build(s);outgoing=defaultdict(list)
    for u,v,cap,kind,ref in arcs:
        if kind in ('backbone','terminal_backbone','country_accounting'):outgoing[u].append(v)
    mat=[]
    for t in model.keys:
        seen={t};q=deque([t])
        while q:
            for v in outgoing[q.popleft()]:
                if v not in seen:seen.add(v);q.append(v)
        mat.append([int('DEMAND:'+co in seen) for co in model.dem.Country])
    ax.pcolormesh(np.arange(23)-.5,np.arange(10)-.5,np.asarray(mat),cmap=ListedColormap(['#EDF0F3',BLUE]),vmin=0,vmax=1,edgecolors='white',linewidth=.5)
    ax.set_ylim(8.5,-.5);ax.set_xlim(-.5,21.5)
    ax.set_yticks(range(9),[LABEL[t] for t in model.keys]);ax.set_xticks(range(22),[ISO[c] for c in model.dem.Country],rotation=0)
    ax.set_title(f'({panel}) {year}, {level}',loc='left',pad=9);ax.set_ylabel('Terminal group');ax.set_xlabel('Demand country')
    ax.set_xticks(np.arange(-.5,22,1),minor=True);ax.set_yticks(np.arange(-.5,9,1),minor=True);ax.grid(which='minor',color='white',linewidth=.5);ax.tick_params(which='minor',bottom=False,left=False)
save(fig,1)

# 2. Literal annual interface capacities, zero records visible as small end ticks.
fig,axes=plt.subplots(1,2,figsize=(7.1,4.7),sharey=True,layout='constrained')
for ax,year,panel in zip(axes,[2030,2040],['a','b']):
    e=model.e[model.e.year.eq(year)&model.e.edge_type.eq('terminal_backbone')].set_index('from_node').reindex(model.keys)
    y=np.arange(9)
    for offset,col,color,label in [(-.17,'capacity_pci_pmi_gwh_per_day',BLUE,'PCI/PMI'),(.17,'capacity_advanced_gwh_per_day',ORANGE,'Advanced')]:
        vals=e[col].to_numpy()*365/1000;ax.barh(y+offset,vals,height=.29,color=color,label=label)
    ax.set_yticks(y,[LABEL[t] for t in model.keys]);ax.invert_yaxis();ax.set_xlim(0,90);ax.set_xticks([0,30,60,90]);ax.set_xlabel('Capacity (TWh/year)');ax.set_title(f'({panel}) {year}',loc='left');tidy(ax)
axes[0].set_ylim(8.5,-.5)
axes[0].legend(loc='lower left',bbox_to_anchor=(0,1.08),ncol=2,frameon=False);save(fig,2)

# 3. Quantile envelopes are scenario ranges, not confidence intervals.
fig,axes=plt.subplots(1,2,figsize=(7.1,3.8),sharey=True,layout='constrained')
for ax,year,panel in zip(axes,[2030,2040],['a','b']):
    for level,color,mark in [('PCI/PMI',BLUE,'o'),('Advanced',ORANGE,'s')]:
        f=S[S.year.eq(year)&S.level.eq(level)&S.configuration.eq('graph')]
        g=f.groupby('import_share').unmet_pct;lo=g.min();hi=g.max();med=f[f['quantile'].eq(.5)].set_index('import_share').sort_index().unmet_pct
        ax.fill_between(lo.index*100,100-hi,100-lo,color=color,alpha=.13)
        ax.plot(med.index*100,100-med,marker=mark,color=color,label=level)
    ax.set_xticks([10,20,30,100]);ax.set_ylim(0,103);ax.set_xlabel('Import target (%)');ax.set_title(f'({panel}) {year}',loc='left');ax.grid(color='#E3E7EB',linewidth=.6)
axes[0].set_ylabel('Target served (%)');axes[0].legend(frameon=False,loc='lower left',bbox_to_anchor=(0,1.09),ncol=2);save(fig,3)

# 4. Joint location bounds; separate source-only bounds are disclosed in the text.
fig,ax=plt.subplots(figsize=(7.1,5.4),layout='constrained');y=np.arange(len(J))
lo=100*J.joint_lower_served_gwh/J.target_gwh;hi=100*J.optimistic_served_gwh/J.target_gwh
ax.hlines(y,lo,hi,color=GREY,linewidth=2);ax.scatter(lo,y,color=RED,s=36,label='Joint assignment lower bound',zorder=3);ax.scatter(hi,y,color=BLUE,s=36,label='Free assignment upper bound',zorder=3)
labels=[s.replace('_PCIPMI_','  PCI/PMI  Q').replace('_Advanced_','  Advanced  Q').replace('0.25','25').replace('0.5','50').replace('0.75','75') for s in J.scenario_id]
ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlim(30,103);ax.set_xlabel('Target served (%)');tidy(ax);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),frameon=False,ncol=1);save(fig,4)

# 5. Refresh the carrier layer only, explicitly retain the 2024 graph.
V=pd.read_csv(R/'cross_vintage_stress.csv');fig,axes=plt.subplots(1,2,figsize=(7.1,4.4),sharey=True,layout='constrained')
for ax,year,panel in zip(axes,[2030,2040],['a','b']):
    f=V[V.import_share.eq(.2)&V.scenario_id.str.startswith(str(year))];ids=[s['scenario_id'] for s in model.scenarios if s['year']==year];y=np.arange(6)
    for off,ver,color,label in [(-.17,'frozen_2024',BLUE,'2024 carrier records'),(.17,'matched_2026_carriers_2024_network',ORANGE,'Matched 2026 refresh')]:
        g=f[f.version.eq(ver)].set_index('scenario_id').reindex(ids);ax.barh(y+off,100-g.unmet_pct,height=.29,color=color,label=label)
    ax.set_yticks(y,[s.split('_')[1]+' Q'+s.split('_')[2].replace('0.25','25').replace('0.5','50').replace('0.75','75') for s in ids]);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('Target served (%)');ax.set_title(f'({panel}) {year}',loc='left');tidy(ax)
axes[0].legend(loc='lower left',bbox_to_anchor=(0,1.07),frameon=False,ncol=1);save(fig,5)

# 6. No claim that a padded zero-capacity fourth interface is useful in the free case.
B=pd.read_csv(R/'budget_frontier.csv');fig,ax=plt.subplots(figsize=(7.1,3.7),layout='constrained')
ax.plot(B.budget,B.optimistic_unmet_pct,'o-',color=BLUE,label='Free terminal assignment');ax.plot(B.budget,B.mapping_unmet_pct,'s--',color=ORANGE,label='Adverse terminal assignment')
ax.set_xticks(range(1,10));ax.set_ylim(0,65);ax.set_xlabel('Number of admitted terminal interfaces');ax.set_ylabel('Worst scenario unmet target (%)');ax.grid(color='#E3E7EB',linewidth=.6);ax.legend(frameon=False,loc='lower left',bbox_to_anchor=(0,1.01));save(fig,6)

# 7. Report the entire tie set, not an arbitrary deterministic solution.
four=C[C.budget.eq(4)];op=pd.read_csv(R/'optimistic_optimal_portfolios.csv');det=pd.read_csv(R/'central_optimal_portfolios.csv');merged=four.merge(MP[MP.budget.eq(4)],on='selection',suffixes=('','_mapping'))
base=pd.read_csv(R/'strong_baselines.csv');groups=[]
for name,sels in [('Capacity rank',[base[base.method.eq('capacity_rank')].iloc[0].selection]),('Greedy',[base[base.method.eq('greedy')].iloc[0].selection]),('Minimax optima (6)',op.selection),('Central optima (77)',det.selection),('Mapping minimax',[';'.join(SUMMARY['mapping_selection'])])]:
    g=merged[merged.selection.isin(sels)];groups.append((name,g.worst_unmet_pct.min(),g.worst_unmet_pct.max(),g.mapping_worst_unmet_pct.min(),g.mapping_worst_unmet_pct.max()))
fig,ax=plt.subplots(figsize=(7.1,3.8),layout='constrained')
for i,(name,a,b,c,d) in enumerate(groups):
    ax.plot([a,b],[i-.12]*2,color=BLUE,linewidth=3,marker='o');ax.plot([c,d],[i+.12]*2,color=ORANGE,linewidth=3,marker='s')
ax.plot([],[],color=BLUE,marker='o',label='Free assignment');ax.plot([],[],color=ORANGE,marker='s',label='Adverse assignment')
ax.set_yticks(range(len(groups)),[x[0] for x in groups]);ax.invert_yaxis();ax.set_xlim(0,105);ax.set_xlabel('Worst scenario unmet target (%)');tidy(ax);ax.legend(frameon=False,loc='lower left',bbox_to_anchor=(0,1.01),ncol=2);save(fig,7)

# 8. Maturity, capacity and conversion assumptions on a fixed graph and sample.
fig,axes=plt.subplots(1,2,figsize=(7.1,4.3),sharey=True,layout='constrained')
configs=[('graph','All disclosed projects'),('advanced_carriers','Advanced projects only'),('conversion_adjusted','Reported yield adjustment'),('additive_phases','Additive phase sensitivity'),('duplicated_pool','Duplicated pool ablation')]
for ax,share,panel in zip(axes,[.2,1.],['a','b']):
    f=S[S.year.eq(2040)&S.level.eq('Advanced')&S['quantile'].eq(.5)&S.import_share.eq(share)].set_index('configuration');y=np.arange(len(configs));vals=[100-f.loc[k,'unmet_pct'] for k,l in configs]
    ax.barh(y,vals,color=[BLUE,ORANGE,GREEN,GREY,GREY]);ax.set_yticks(y,[l for k,l in configs]);ax.invert_yaxis();ax.set_xlim(0,110);ax.set_xlabel('Target served (%)');ax.set_title(f'({panel}) {int(share*100)}% import target',loc='left');tidy(ax)
    for i,v in enumerate(vals):ax.text(v+1,i,f'{v:.1f}',va='center',fontsize=10)
axes[0].set_ylim(4.5,-.5);save(fig,8)

# 9. Outage stresses use the mapping-aware four-interface set. No failure probabilities.
sel=set(SUMMARY['mapping_selection']);out=[]
for fail in [None]+sorted(sel):
    chosen=sel-({fail} if fail else set());free=max(x[2] for x in evaluate(model,chosen));adverse=max(max(x[2] for x in evaluate(model,chosen,mapping=mp)) for mp in model.mapping_cases)
    out.append(dict(failed=fail or 'none',free_unmet_pct=free,mapping_unmet_pct=adverse))
O=pd.DataFrame(out);csv(O,'outage_mapping_results.csv');fig,ax=plt.subplots(figsize=(7.1,3.8),layout='constrained');y=np.arange(len(O))
ax.barh(y-.17,O.free_unmet_pct,height=.29,color=BLUE,label='Free assignment');ax.barh(y+.17,O.mapping_unmet_pct,height=.29,color=ORANGE,label='Adverse assignment');ax.set_yticks(y,['No outage']+['Remove '+LABEL[t] for t in sorted(sel)]);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('Worst scenario unmet target (%)');tidy(ax);ax.legend(frameon=False,loc='lower left',bbox_to_anchor=(0,1.01),ncol=2);save(fig,9)

js(A/'figure_canvas_checks.json',QA)
js(P/'figure_evidence_manifest.json',{'source_hashes':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(R.glob('*.csv'))},'figures':QA})
