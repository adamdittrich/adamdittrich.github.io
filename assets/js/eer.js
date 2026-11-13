/* Copyright (c) 2026 Adam Dittrich. MIT licence; see assets/files/datasets/eer-analysis/LICENSE.txt. */
/* Annual Czechoslovak EER explorer. Source observations remain unchanged. */
(() => {
  'use strict';
  const root = document.querySelector('.eer-explorer');
  if (!root) return;
  const $ = id => root.querySelector('#' + id);
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = {neer:'#286f95',reer:'#bf6b2e',price:'#80527f',exports:'#3a8278',imports:'#b56b33',total:'#48698c',direct:'#60855a',selected:'#963f5b',band:'#a8b8cd'};
  const BASIS = {TWEER:'Total-trade weights',XEER:'Export weights',MEER:'Import weights'};
  const METHOD = {
    paasche:{label:'Current-year geometric chain',note:'Annual bilateral log changes are weighted by current-year trade shares. This is the preferred specification.'},
    laspeyres:{label:'Lagged-year geometric chain',note:'Annual bilateral log changes are weighted by the preceding year’s trade shares.'},
    tornqvist:{label:'Törnqvist chain',note:'Annual bilateral log changes use the average of current-year and preceding-year trade shares.'},
    fixed1929:{label:'Fixed-1929-weight chain',note:'Bilateral log changes use the same 1929 partner weights throughout. The display reference year can be changed independently of these fixed weights.'},
    direct_current:{label:'Direct current-weighted index',note:'The direct index uses current-year weights on bilateral levels relative to the original reference year. It is supplied for total trade. Its year-to-year movements also reflect changes in weights.'}
  };
  const CHAINS = ['paasche','laspeyres','tornqvist','fixed1929'];
  const CHART_IDS = ['headline','sensitivity','relative','decomposition','tradebasis','weights','coverage'];
  const state = {ready:false,valid:false,data:null,lookup:new Map(),rows:[],years:[],basis:'TWEER',method:'paasche',measure:'both',display:'levels',base:1929,inspectYear:1929,partner:'Germany',charts:new Map(),configs:new Map(),dialogChart:null,dialogTrigger:null};
  window.EER_EXPLORER = {ready:false};
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = (value,digits=2) => finite(value) ? new Intl.NumberFormat('en-GB',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value) : '—';
  const signed = (value,digits=2) => (finite(value)&&value>0?'+':'')+fmt(value,digits);
  const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const methodLabel = (method=state.method) => METHOD[method].label;
  const rangeLabel = () => state.years.length ? `${state.years[0]}–${state.years.at(-1)}` : '';
  const baseLabel = () => `${state.base} = 100`;
  const allRows = (basis=state.basis,method=state.method) => state.lookup.get(`${basis}|${method}`)||[];
  const sourceRow = (year,basis=state.basis,method=state.method) => allRows(basis,method).find(row=>row.year===year);
  const selectedYears = rows => rows.filter(row=>state.years.includes(row.year));
  const chainMethod = () => state.method==='direct_current'?'paasche':state.method;
  const weightKey = () => ({TWEER:'total_trade_weight',XEER:'export_weight',MEER:'import_weight'}[state.basis]);

  function el(tag,attrs={},content) {
    const node=document.createElementNS(NS,tag);
    for(const [key,value] of Object.entries(attrs)) if(value!==undefined && value!==null) node.setAttribute(key,String(value));
    if(content!==undefined) node.textContent=content;
    return node;
  }
  function text(svg,x,y,label,attrs={}) { svg.append(el('text',{x,y,fill:'#536872','font-family':'Segoe UI,Arial,sans-serif','font-size':11,...attrs},label)); }
  function line(svg,x1,y1,x2,y2,attrs={}) { svg.append(el('line',{x1,y1,x2,y2,stroke:'#e5e1d8','stroke-width':1,...attrs})); }
  function normalized(row,basis=state.basis,method=state.method) {
    if(!row) return null;
    const base=sourceRow(state.base,basis,method);
    const ratio=(a,b)=>finite(a)&&finite(b)&&b>0?100*(a/b):null;
    return {...row,
      neer_level:ratio(row.neer,base?.neer),reer_level:ratio(row.reer,base?.reer),
      price_level:ratio(row.relative_price_index,base?.relative_price_index),
      neer_average:ratio(row.neer_ma3,base?.neer),reer_average:ratio(row.reer_ma3,base?.reer)
    };
  }
  function seriesValue(row,metric,basis=state.basis,method=state.method) {
    if(!row) return null;
    return state.display==='yoy'?row[metric+'_yoy_pct']:normalized(row,basis,method)[metric+'_level'];
  }
  function levelLog(rows,keys) {
    return rows.some(row=>row.year<=1923 && keys.some(key=>finite(row[key])&&row[key]>0));
  }
  function legendHTML(items) {
    return items.map(item=>`<span><i class="${item.type==='band'?'eer-band':item.type==='square'?'eer-square':item.dash?'eer-dashed':''}" style="--eer-color:${item.color}"></i>${esc(item.label)}</span>`).join('');
  }
  function configureCharts() {
    state.configs.clear();
    const level=state.display==='levels',unit=level?`Index, ${baseLabel()}`:'Change from the preceding year (%)';
    const visible=state.measure==='both'?['neer','reer']:[state.measure];
    const average=level&&$('eer-smooth').checked;
    const mainSeries=visible.map(metric=>({key:metric+(level?'_level':'_yoy_pct'),label:metric.toUpperCase(),color:COLORS[metric],dash:metric==='reer'?'7 3':undefined}));
    if(average) mainSeries.push(...visible.map(metric=>({key:metric+'_average',label:metric.toUpperCase()+' 3-year average',color:COLORS[metric],dash:'2 4',width:2,points:false})));
    const mainLegend=visible.map(metric=>({label:metric.toUpperCase()+' annual',color:COLORS[metric],dash:metric==='reer'}));
    if(average) mainLegend.push({label:'3-year averages (dotted)',color:'#687b83',dash:true});
    state.configs.set('headline',{title:'Nominal and real effective exchange rates',unit,rows:state.rows,series:mainSeries,legend:mainLegend,baseline:level?100:0,log:level&&levelLog(state.rows,visible.map(m=>m+'_level')),
      caption:`${BASIS[state.basis]} · ${methodLabel()}. ${level?'Higher levels indicate depreciation.':'Positive annual changes indicate depreciation; negative changes indicate appreciation.'} ${average?'The centered three-year averages are descriptive overlays; annual observations remain visible.':''}`});

    const metric=state.measure==='neer'?'neer':'reer';
    const sensitivity=state.years.map(year=>{
      const values=CHAINS.map(method=>seriesValue(sourceRow(year,state.basis,method),metric,state.basis,method));
      return {year,preferred:values[0],selected:seriesValue(sourceRow(year),metric),direct:state.basis==='TWEER'?seriesValue(sourceRow(year,'TWEER','direct_current'),metric,'TWEER','direct_current'):null,low:values.every(finite)?Math.min(...values):null,high:values.every(finite)?Math.max(...values):null};
    });
    const sensitivitySeries=[{key:'preferred',label:'Current-year chain',color:COLORS.total}];
    const sensitivityLegend=[{label:'Range of four chains',color:COLORS.band,type:'band'},{label:'Current-year chain',color:COLORS.total}];
    if(!['paasche','direct_current'].includes(state.method)) {sensitivitySeries.push({key:'selected',label:methodLabel(),color:COLORS.selected});sensitivityLegend.push({label:methodLabel(),color:COLORS.selected});}
    if(state.basis==='TWEER') {sensitivitySeries.push({key:'direct',label:'Direct current-weighted',color:COLORS.direct,dash:'5 4'});sensitivityLegend.push({label:'Direct current-weighted',color:COLORS.direct,dash:true});}
    state.configs.set('sensitivity',{title:'How the formula changes the result',unit:`${metric.toUpperCase()} · ${unit}`,rows:sensitivity,series:sensitivitySeries,legend:sensitivityLegend,baseline:level?100:0,band:{low:'low',high:'high',color:COLORS.band},log:level&&levelLog(sensitivity,['low','high','direct']),
      caption:`${BASIS[state.basis]}. The shaded range spans the current-year, lagged-year, Törnqvist and fixed-1929-weight chains. It describes specification sensitivity, not a confidence interval.${state.basis==='TWEER'?' The direct-current index is shown separately.':''}`});

    state.configs.set('relative',{title:state.method==='direct_current'?'Real-to-nominal ratio':'Chained relative-price component',unit:`100 × REER / NEER · ${baseLabel()}`,rows:state.rows,series:[{key:'price_level',label:state.method==='direct_current'?'Real-to-nominal ratio':'Relative-price component',color:COLORS.price}],legend:[{label:state.method==='direct_current'?'Real-to-nominal ratio':'Chained relative-price component',color:COLORS.price}],baseline:100,log:levelLog(state.rows,['price_level']),
      caption:state.method==='direct_current'?`${BASIS[state.basis]} · ${methodLabel()}. This is the ratio of the matched real and nominal indices. Changes combine relative-price developments with changes in weights.`:`${BASIS[state.basis]} · ${methodLabel()}. A fall means that relative-price movements reduced real depreciation relative to nominal depreciation. This is a cumulative chained component, rather than a current-weighted CPI level ratio.`});

    const decomposition=state.years.map(year=>{
      const row=sourceRow(year,state.basis,chainMethod()),available=finite(row?.reer_log_change)&&finite(row?.neer_log_change)&&finite(row?.relative_price_log_change);
      return {year,nominal:available?row.neer_log_change:null,price:available?row.relative_price_log_change:null,real:available?row.reer_log_change:null};
    });
    state.configs.set('decomposition',{title:'What contributes to the real change?',unit:'Annual log changes · 100 × Δ ln(index)',rows:decomposition,kind:'decomposition',series:[{key:'nominal',label:'Nominal component',color:COLORS.neer},{key:'price',label:'Relative-price component',color:COLORS.price},{key:'real',label:'Real change',color:COLORS.reer}],legend:[{label:'Nominal component',color:COLORS.neer,type:'square'},{label:'Relative-price component',color:COLORS.price,type:'square'},{label:'Real change',color:COLORS.reer}],baseline:0,
      caption:`${BASIS[state.basis]} · ${methodLabel(chainMethod())}. Nominal and relative-price log changes add exactly to the real log change. This is an accounting decomposition.${state.method==='direct_current'?' The preferred chain is used in this panel because direct-current changes also include reweighting effects.':''}`});

    const tradeRows=state.years.map(year=>({year,exports:seriesValue(sourceRow(year,'XEER',chainMethod()),'reer','XEER',chainMethod()),imports:seriesValue(sourceRow(year,'MEER',chainMethod()),'reer','MEER',chainMethod()),total:seriesValue(sourceRow(year,'TWEER',chainMethod()),'reer','TWEER',chainMethod())}));
    state.configs.set('tradebasis',{title:'Export and import perspectives',unit:`REER · ${unit}`,rows:tradeRows,series:[{key:'exports',label:'Export weights',color:COLORS.exports},{key:'imports',label:'Import weights',color:COLORS.imports,dash:'6 3'},{key:'total',label:'Total-trade weights',color:COLORS.total,dash:'2 4',width:1.7}],legend:[{label:'Export weights',color:COLORS.exports},{label:'Import weights',color:COLORS.imports,dash:true},{label:'Total-trade weights',color:COLORS.total,dash:true}],baseline:level?100:0,log:level&&levelLog(tradeRows,['exports','imports','total']),
      caption:`${methodLabel(chainMethod())}. Each series uses the same formula and reference year with a different trade basis.${state.method==='direct_current'?' The preferred chain is shown here; a direct-current variant is supplied only for total trade.':''}`});

    state.configs.set('weights',{title:'Which partners make up the basket?',unit:`${BASIS[state.basis]} · % of included basket`,kind:'heatmap',rows:[],series:[],legend:[],caption:'Partner shares sum to 100% within the fourteen-partner basket. Partners are ordered by their 1929 weight for the selected trade basis. Point to a cell to inspect its exact weight; the national coverage of the basket is shown separately below.'});
    const coverage=selectedYears(state.data.coverage).map(row=>({year:row.year,exports:100*row.export_coverage,imports:100*row.import_coverage,total:100*row.total_trade_coverage}));
    const covSeries=[{key:'exports',label:'Exports',color:COLORS.exports},{key:'imports',label:'Imports',color:COLORS.imports,dash:'6 3'},{key:'total',label:'Total trade',color:COLORS.total,dash:'2 4'}];
    const active=({TWEER:'total',XEER:'exports',MEER:'imports'})[state.basis];
    covSeries.forEach(series=>series.width=series.key===active?3.1:1.8);
    state.configs.set('coverage',{title:'How much national trade does the basket cover?',unit:'Share of national trade (%) · vertical axis 70–100%',rows:coverage,series:covSeries,legend:covSeries,scale:{low:70,high:100,values:[70,75,80,85,90,95,100],step:5},caption:'Published basket shares of national exports, imports and total trade. The thicker line corresponds to the selected trade basis. Coverage and normalised within-basket partner weights measure different quantities.'});
  }

  function niceScale(min,max) {
    if(min===max) {const spread=Math.abs(min)*.06||1;min-=spread;max+=spread;}
    const pad=(max-min)*.07;min-=pad;max+=pad;
    const raw=(max-min)/4.5,power=10**Math.floor(Math.log10(raw)),fraction=raw/power;
    const step=(fraction<=1?1:fraction<=2?2:fraction<=2.5?2.5:fraction<=5?5:10)*power;
    const low=Math.floor(min/step)*step,high=Math.ceil(max/step)*step,values=[];
    for(let v=low;v<=high+step*.001;v+=step) values.push(Math.abs(v)<step*.0001?0:v);
    return {low,high,values,step};
  }
  function logScale(values) {
    const usable=values.filter(v=>v>0),min=Math.min(...usable),max=Math.max(...usable);
    let low=Math.floor(Math.log10(min)),high=Math.ceil(Math.log10(max));
    if(low===high) {low-=1;high+=1;}
    const step=Math.max(1,Math.ceil((high-low)/6)),ticks=[];
    for(let n=low;n<=high;n+=step) ticks.push(10**n);
    if(ticks.at(-1)<10**high) ticks.push(10**high);
    return {low:10**low,high:10**high,values:ticks,step:0,log:true};
  }
  function tickLabel(value,scale) {
    if(Math.abs(value)>=1e6 || (value!==0 && Math.abs(value)<.001)) return value.toExponential(0).replace('e+','e');
    if(Math.abs(value)>=1e3) return fmt(value/1e3,Math.abs(value)%1e3?1:0)+'k';
    return fmt(value,scale.log?Math.max(0,-Math.floor(Math.log10(value))):scale.step<1?Math.min(3,Math.ceil(-Math.log10(scale.step))):value%1?1:0);
  }
  function yearTicks(width) {
    const years=state.years,max=width<400?4:width<650?6:10,step=Math.max(1,Math.ceil((years.length-1)/(max-1)));
    return years.filter((year,index)=>index%step===0 || index===years.length-1);
  }
  function path(rows,key,X,Y,log=false) {
    let d='',active=false;
    rows.forEach(row=>{const value=row[key];if(!finite(value)||(log&&value<=0)){active=false;return;}d+=(active?' L':' M')+X(row.year).toFixed(2)+' '+Y(value).toFixed(2);active=true;});
    return d;
  }
  function bandPath(rows,band,X,Y) {
    const groups=[];let group=[];
    rows.forEach(row=>{if(finite(row[band.low])&&finite(row[band.high]))group.push(row);else if(group.length){groups.push(group);group=[];}});
    if(group.length)groups.push(group);
    return groups.map(part=>part.map((row,index)=>(index?'L':'M')+X(row.year)+' '+Y(row[band.high])).join(' ')+part.slice().reverse().map(row=>'L'+X(row.year)+' '+Y(row[band.low])).join(' ')+'Z').join(' ');
  }
  function emptyChart(host,message) {
    host.replaceChildren();
    const width=Math.max(240,host.clientWidth||500),svg=el('svg',{xmlns:NS,viewBox:`0 0 ${width} 190`,width,height:190,role:'img','aria-label':message});
    text(svg,width/2,88,'No complete observations in this selection.',{'text-anchor':'middle','font-size':width<350?10:12});
    text(svg,width/2,112,message,{'text-anchor':'middle','font-size':width<350?9:11});
    host.append(svg);return svg;
  }
  function bindInspection(svg,X,width,margin,rows,callback) {
    const first=state.years[0],last=state.years.at(-1);
    const inspect=event=>{
      const rect=svg.getBoundingClientRect(),px=(event.clientX-rect.left)*width/rect.width;
      if(px<margin.left||px>width-margin.right)return;
      const year=first===last?first:Math.round(first+(px-margin.left)/(width-margin.left-margin.right)*(last-first));
      if(callback) callback(event,year,rect); else inspectYear(year);
    };
    svg.addEventListener('pointermove',event=>{if(event.pointerType!=='touch')inspect(event);});
    svg.addEventListener('pointerdown',inspect);
    svg.addEventListener('keydown',event=>{
      let year=state.inspectYear;
      if(event.key==='ArrowLeft')year--;else if(event.key==='ArrowRight')year++;else if(event.key==='Home')year=first;else if(event.key==='End')year=last;else return;
      event.preventDefault();inspectYear(Math.max(first,Math.min(last,year)));
    });
  }

  function renderChart(id,host=$('eer-chart-'+id),enlarged=false) {
    const config=state.configs.get(id);
    if(!config)return;
    state.charts.delete(host.id);
    if(config.kind==='heatmap')return renderHeatmap(host,enlarged);
    host.classList.remove('eer-heatmap');
    const values=config.rows.flatMap(row=>config.series.map(series=>row[series.key])).filter(finite);
    if(config.band) values.push(...config.rows.flatMap(row=>[row[config.band.low],row[config.band.high]]).filter(finite));
    if(!values.length) {emptyChart(host,'Choose a year with available data.');return;}
    if(config.baseline!==undefined)values.push(config.baseline);
    if(config.kind==='decomposition')config.rows.forEach(row=>{if(finite(row.nominal)&&finite(row.price)){values.push(Math.max(0,row.nominal)+Math.max(0,row.price));values.push(Math.min(0,row.nominal)+Math.min(0,row.price));}});
    host.replaceChildren();
    const width=Math.max(240,Math.round(host.clientWidth||600));
    const height=enlarged?Math.min(550,Math.max(310,Math.round(window.innerHeight*.53))):id==='headline'?width<450?280:345:id==='coverage'?width<450?265:295:width<400?255:280;
    const margin={left:width<350?45:54,right:15,top:29,bottom:35};
    const svg=el('svg',{xmlns:NS,viewBox:`0 0 ${width} ${height}`,width,height,role:'img',tabindex:0,'aria-label':`${config.title}. ${config.unit}. ${rangeLabel()}. Use arrow keys to inspect years.`});
    svg.append(el('title',{},config.title));svg.append(el('desc',{},`${config.unit}. ${config.caption} The annual data tables provide exact values.`));
    const scale=config.scale||(config.log?logScale(values):niceScale(Math.min(...values),Math.max(...values)));
    const first=state.years[0],last=state.years.at(-1);
    const X=year=>first===last?(margin.left+width-margin.right)/2:margin.left+(year-first)/(last-first)*(width-margin.left-margin.right);
    const Y=value=>height-margin.bottom-(scale.log?(Math.log10(value)-Math.log10(scale.low))/(Math.log10(scale.high)-Math.log10(scale.low)):(value-scale.low)/(scale.high-scale.low))*(height-margin.top-margin.bottom);
    text(svg,margin.left,14,scale.log?'Logarithmic scale':config.kind==='decomposition'?'Log points':config.unit.includes('(%)')?'%':config.unit.startsWith('100')?baseLabel():state.display==='yoy'&&['headline','sensitivity','tradebasis'].includes(id)?'%':baseLabel(),{'font-size':10});
    for(const value of scale.values){line(svg,margin.left,Y(value),width-margin.right,Y(value));text(svg,margin.left-7,Y(value)+3.5,tickLabel(value,scale),{'text-anchor':'end','font-size':10});}
    for(const year of yearTicks(width)){line(svg,X(year),height-margin.bottom,X(year),height-margin.bottom+4,{stroke:'#a4a99e'});text(svg,X(year),height-12,String(year),{'text-anchor':'middle','font-size':10});}
    if(config.baseline!==undefined&&(!scale.log||config.baseline>0))line(svg,margin.left,Y(config.baseline),width-margin.right,Y(config.baseline),{stroke:'#8c8c7c','stroke-width':1.2,'stroke-dasharray':'4 4'});
    if(config.band)svg.append(el('path',{d:bandPath(config.rows,config.band,X,Y),fill:config.band.color,'fill-opacity':.35,stroke:'none'}));
    if(config.kind==='decomposition'){
      const barWidth=Math.min(34,(width-margin.left-margin.right)/Math.max(2,state.years.length)*.65);
      for(const row of config.rows){if(!finite(row.nominal)||!finite(row.price))continue;let positive=0,negative=0;
        for(const series of config.series.slice(0,2)){const value=row[series.key],start=value>=0?positive:negative,end=start+value;if(value>=0)positive=end;else negative=end;
          const rect=el('rect',{x:X(row.year)-barWidth/2,y:Math.min(Y(start),Y(end)),width:barWidth,height:Math.max(.4,Math.abs(Y(start)-Y(end))),fill:series.color,'fill-opacity':.8});rect.append(el('title',{},`${row.year} · ${series.label}: ${signed(value)} log points`));svg.append(rect);
        }
      }
    }
    for(const series of config.series){
      if(config.kind==='decomposition'&&series.key!=='real')continue;
      svg.append(el('path',{d:path(config.rows,series.key,X,Y,scale.log),fill:'none',stroke:series.color,'stroke-width':series.width||2.3,'stroke-dasharray':series.dash,'stroke-linecap':'round','stroke-linejoin':'round'}));
      if(series.points!==false)for(const row of config.rows)if(finite(row[series.key])&&(!scale.log||row[series.key]>0)){
        const dot=el('circle',{cx:X(row.year),cy:Y(row[series.key]),r:state.years.length>16?2.4:2.8,fill:'#fff',stroke:series.color,'stroke-width':1.5});dot.append(el('title',{},`${row.year} · ${series.label}: ${fmt(row[series.key])}`));svg.append(dot);
      }
    }
    const marker=el('g',{'pointer-events':'none'});svg.append(marker);
    state.charts.set(host.id,{id,svg,config,marker,X,Y,width,height,margin,scale});
    bindInspection(svg,X,width,margin,config.rows);
    host.append(svg);
  }

  function heatColor(value,max) {
    const fraction=Math.max(0,Math.min(1,value/max)),light=[242,241,228],dark=[31,104,116];
    return '#'+light.map((v,i)=>Math.round(v+(dark[i]-v)*fraction).toString(16).padStart(2,'0')).join('');
  }
  function renderHeatmap(host,enlarged=false) {
    host.replaceChildren();host.classList.add('eer-heatmap');
    const config=state.configs.get('weights'),key=weightKey();
    const width=Math.max(640,Math.round(host.clientWidth||900)),margin={left:142,right:17,top:31,bottom:55};
    const partners=state.data.partners.slice().sort((a,b)=>{
      const av=state.data.weights.find(row=>row.year===1929&&row.partner===a)?.[key]||0;
      const bv=state.data.weights.find(row=>row.year===1929&&row.partner===b)?.[key]||0;
      return bv-av;
    });
    const rowHeight=enlarged?27:24,height=margin.top+partners.length*rowHeight+margin.bottom;
    const cellWidth=(width-margin.left-margin.right)/state.years.length;
    const max=Math.ceil(Math.max(...state.data.weights.map(row=>100*row[key]))/10)*10;
    const svg=el('svg',{xmlns:NS,viewBox:`0 0 ${width} ${height}`,width,height,role:'img',tabindex:0,'aria-label':`${config.title}. ${config.unit}. ${rangeLabel()}. Use arrow keys to inspect years.`});
    svg.append(el('title',{},config.title));svg.append(el('desc',{},config.caption));
    const X=year=>margin.left+(state.years.indexOf(year)+.5)*cellWidth;
    for(const year of state.years)text(svg,X(year),17,String(year),{'text-anchor':'middle','font-size':state.years.length>16?9:10});
    partners.forEach((partner,pIndex)=>{
      const y=margin.top+pIndex*rowHeight;
      text(svg,margin.left-9,y+rowHeight/2+3.5,partner,{'text-anchor':'end','font-size':11});
      for(const year of state.years){
        const row=state.data.weights.find(record=>record.year===year&&record.partner===partner),value=finite(row?.[key])?100*row[key]:null;
        const cell=el('rect',{x:X(year)-cellWidth/2+.7,y:y+.7,width:cellWidth-1.4,height:rowHeight-1.4,fill:finite(value)?heatColor(value,max):'#f1f0ec'});
        cell.append(el('title',{},`${partner} · ${year}: ${fmt(value)}% of included basket`));svg.append(cell);
        if(state.years.length<=8&&finite(value))text(svg,X(year),y+rowHeight/2+3.5,fmt(value,1),{'text-anchor':'middle','font-size':10,fill:value>max*.58?'#fff':'#345965'});
      }
    });
    const legendY=height-25,legendWidth=Math.min(260,width-margin.left-margin.right-85),pieces=50;
    text(svg,margin.left,legendY-10,'Weight within basket (%)',{'font-size':10});
    for(let i=0;i<pieces;i++)svg.append(el('rect',{x:margin.left+i/pieces*legendWidth,y:legendY,width:legendWidth/pieces+.2,height:9,fill:heatColor(i/(pieces-1)*max,max)}));
    text(svg,margin.left,legendY+22,'0',{'font-size':10});text(svg,margin.left+legendWidth,legendY+22,String(max),{'font-size':10,'text-anchor':'end'});
    const marker=el('g',{'pointer-events':'none'});svg.append(marker);
    state.charts.set(host.id,{id:'weights',svg,config,marker,X,width,height,margin,cellWidth,rowHeight,partners});
    const inspect=event=>{
      const rect=svg.getBoundingClientRect(),px=(event.clientX-rect.left)*width/rect.width,py=(event.clientY-rect.top)*height/rect.height;
      if(px<margin.left||px>width-margin.right||py<margin.top||py>=margin.top+partners.length*rowHeight)return;
      const yearIndex=Math.min(state.years.length-1,Math.floor((px-margin.left)/cellWidth));
      state.partner=partners[Math.min(partners.length-1,Math.floor((py-margin.top)/rowHeight))];
      inspectYear(state.years[yearIndex]);
    };
    svg.addEventListener('pointermove',event=>{if(event.pointerType!=='touch')inspect(event);});svg.addEventListener('pointerdown',inspect);
    svg.addEventListener('keydown',event=>{
      let yearIndex=state.years.indexOf(state.inspectYear),partnerIndex=partners.indexOf(state.partner);
      if(event.key==='ArrowLeft')yearIndex--;else if(event.key==='ArrowRight')yearIndex++;else if(event.key==='ArrowUp')partnerIndex--;else if(event.key==='ArrowDown')partnerIndex++;else if(event.key==='Home')yearIndex=0;else if(event.key==='End')yearIndex=state.years.length-1;else return;
      event.preventDefault();state.partner=partners[Math.max(0,Math.min(partners.length-1,partnerIndex))];inspectYear(state.years[Math.max(0,Math.min(state.years.length-1,yearIndex))]);
    });
    host.append(svg);
  }
  function inspectionText(id,year=state.inspectYear) {
    const config=state.configs.get(id);
    if(id==='weights'){
      const row=state.data.weights.find(record=>record.year===year&&record.partner===state.partner);
      return `${year} · ${state.partner}: ${fmt(finite(row?.[weightKey()])?100*row[weightKey()]:null)}% of the included basket · ${BASIS[state.basis]}`;
    }
    const row=config.rows.find(record=>record.year===year);
    if(!row)return String(year);
    let values=config.series.filter(series=>!series.key.endsWith('_average')).map(series=>`${series.label}: ${fmt(row[series.key])}`);
    if(config.band)values.push(`Four-chain range: ${fmt(row.low)}–${fmt(row.high)}`);
    return `${year} · ${values.join(' · ')}`;
  }
  function inspectYear(year) {
    if(!state.valid||!state.years.includes(year))return;
    state.inspectYear=year;
    const row=state.rows.find(record=>record.year===year);
    $('eer-year').value=String(state.years.indexOf(year));$('eer-year').setAttribute('aria-valuetext',String(year));$('eer-selected-year').textContent=String(year);
    const items=[
      {label:`NEER · ${baseLabel()}`,value:fmt(row.neer_level)},
      {label:`REER · ${baseLabel()}`,value:fmt(row.reer_level)},
      {label:`${state.method==='direct_current'?'Real-to-nominal ratio':'Relative-price component'} · ${baseLabel()}`,value:fmt(row.price_level)},
      {label:'NEER annual change',value:signed(row.neer_yoy_pct)+(finite(row.neer_yoy_pct)?'%':'')},
      {label:'REER annual change',value:signed(row.reer_yoy_pct)+(finite(row.reer_yoy_pct)?'%':'')},
      {label:state.method==='direct_current'?'Ratio annual change · log points':'Relative-price annual change · log points',value:signed(row.relative_price_log_change)}
    ];
    $('eer-readout').innerHTML=items.map(item=>`<div><dt>${esc(item.label)}</dt><dd>${esc(item.value)}</dd></div>`).join('');
    $('eer-partner-readout').textContent=inspectionText('weights');
    for(const chart of state.charts.values()){
      chart.marker.replaceChildren();
      const x=chart.X(year);
      if(chart.id==='weights'){
        chart.marker.append(el('rect',{x:x-chart.cellWidth/2,y:chart.margin.top,width:chart.cellWidth,height:chart.partners.length*chart.rowHeight,fill:'none',stroke:'#793a47','stroke-width':1.5}));
        const partnerIndex=chart.partners.indexOf(state.partner);
        if(partnerIndex>=0)chart.marker.append(el('rect',{x:x-chart.cellWidth/2+.5,y:chart.margin.top+partnerIndex*chart.rowHeight+.5,width:chart.cellWidth-1,height:chart.rowHeight-1,fill:'none',stroke:'#793a47','stroke-width':2.5}));
      }else{
        line(chart.marker,x,chart.margin.top,x,chart.height-chart.margin.bottom,{stroke:'#9e9488','stroke-dasharray':'3 3'});
        const point=chart.config.rows.find(record=>record.year===year);
        for(const series of chart.config.series){
          if(chart.config.kind==='decomposition'&&series.key!=='real')continue;
          const value=point?.[series.key];
          if(finite(value)&&(!chart.scale.log||value>0))chart.marker.append(el('circle',{cx:x,cy:chart.Y(value),r:4,fill:'#fff',stroke:series.color,'stroke-width':2}));
        }
      }
    }
    root.querySelectorAll('#eer-table-body tr[aria-current]').forEach(row=>row.removeAttribute('aria-current'));
    $('eer-row-'+year)?.setAttribute('aria-current','true');
    renderMethodTable();
    if(state.dialogChart)$('eer-dialog-readout').textContent=inspectionText(state.dialogChart);
    window.EER_EXPLORER.selectedYear=year;
  }
  function renderMethodTable() {
    $('eer-method-year').textContent=String(state.inspectYear);
    const methods=state.basis==='TWEER'?[...CHAINS,'direct_current']:CHAINS;
    $('eer-method-table-body').innerHTML=methods.map(method=>{
      const row=sourceRow(state.inspectYear,state.basis,method);
      return `<tr${method===state.method?' aria-current="true"':''}><th scope="row">${esc(methodLabel(method))}</th><td class="num">${fmt(seriesValue(row,'neer',state.basis,method))}</td><td class="num">${fmt(seriesValue(row,'reer',state.basis,method))}</td></tr>`;
    }).join('');
    const caption=root.querySelector('.eer-method-table table caption');
    if(caption)caption.textContent=`${state.inspectYear} · ${BASIS[state.basis]} · ${state.display==='levels'?baseLabel():'Annual changes (%)'}`;
    $('eer-method-table-note').textContent='The highlighted row is the selected specification. The direct-current index is available for total trade. A dash denotes an unavailable observation.';
  }
  function renderTable() {
    const caption=root.querySelector('.eer-table-details table caption');
    if(caption)caption.textContent=`${BASIS[state.basis]} · ${methodLabel()} · ${rangeLabel()} · ${baseLabel()}`;
    const keys=['neer_level','reer_level','neer_yoy_pct','reer_yoy_pct','price_level','neer_average','reer_average'];
    $('eer-table-body').innerHTML=state.rows.map(row=>`<tr id="eer-row-${row.year}"><th scope="row">${row.year}</th>${keys.map(key=>`<td class="num">${fmt(row[key])}</td>`).join('')}<td>${esc(row.sample)}</td></tr>`).join('');
    const priceHeader=root.querySelector('.eer-table-details thead')?.querySelectorAll('th')[5];
    if(priceHeader)priceHeader.textContent=state.method==='direct_current'?'Real-to-nominal ratio':'Relative-price component';
    $('eer-table-note').textContent=`Index levels and the ${state.method==='direct_current'?'real-to-nominal ratio':'relative-price component'} use ${baseLabel()}. Three-year averages share the observed-series index scale; the average itself need not equal 100 in the reference year. Annual percentage changes use the preceding calendar year and are independent of rebasing. A dash denotes an unavailable value. CSV exports preserve full numerical precision.${state.method==='direct_current'?' Changes in the direct-current ratio include changes in weights.':''}`;
  }
  function invalidate(message) {
    state.valid=false;state.charts.clear();state.rows=[];
    $('eer-range-error').hidden=false;$('eer-range-error').textContent=message;
    $('eer-download-csv').disabled=true;$('eer-year').disabled=true;
    root.querySelectorAll('[data-eer-enlarge],[data-eer-svg]').forEach(button=>button.disabled=true);
    CHART_IDS.forEach(id=>emptyChart($('eer-chart-'+id),'Choose a valid year range.'));
    $('eer-readout').replaceChildren();$('eer-table-body').replaceChildren();$('eer-method-table-body').replaceChildren();$('eer-partner-readout').textContent='';$('eer-selected-year').textContent='Choose a valid range';
    $('eer-status').textContent=message;window.EER_EXPLORER.rowCount=0;
  }
  function renderAll() {
    if(!state.ready)return;
    const start=Number($('eer-start').value),end=Number($('eer-end').value);
    if(!$('eer-start').value||!$('eer-end').value||!$('eer-start').checkValidity()||!$('eer-end').checkValidity()||!Number.isInteger(start)||!Number.isInteger(end))return invalidate('Choose whole years from 1920 to 1938.');
    if(start>end)return invalidate('The first year must be before or equal to the last year.');
    state.basis=$('eer-basis').value;
    const directOption=$('eer-method').querySelector('[value="direct_current"]');
    directOption.disabled=state.basis!=='TWEER';
    if(state.basis!=='TWEER'&&$('eer-method').value==='direct_current')$('eer-method').value='paasche';
    state.method=$('eer-method').value;state.measure=$('eer-measure').value;state.display=$('eer-display').value;state.base=Number($('eer-base').value);
    state.years=state.data.years.filter(year=>year>=start&&year<=end);
    if(!state.years.length)return invalidate('No observations are available in this range.');
    state.rows=selectedYears(allRows()).map(row=>normalized(row));state.valid=true;
    $('eer-range-error').hidden=true;$('eer-download-csv').disabled=false;$('eer-year').disabled=state.years.length===1;
    $('eer-year').max=String(state.years.length-1);
    $('eer-base').disabled=state.display==='yoy';$('eer-smooth').disabled=state.display==='yoy';
    $('eer-smoothing-note').hidden=!(state.display==='levels'&&$('eer-smooth').checked);
    $('eer-early-note').hidden=!state.years.some(year=>year<1925);
    $('eer-early-note').textContent=state.display==='levels'?'The early extension is included. Level panels containing observations from 1920–1923 use a logarithmic scale; equal vertical steps represent proportional changes. Source observations and sample designations are preserved.':'The early extension is included. Annual changes are calculated from the released observations; exceptionally large changes are retained. Source observations and sample designations are preserved.';
    $('eer-method-note').textContent=METHOD[state.method].note+' '+(state.display==='levels'?`Rebasing changes the displayed reference level; it does not change annual growth rates.`:'Annual changes are calculated against the preceding calendar year, including when that year lies outside the displayed range.');
    $('eer-status').textContent=`${state.years.length} years selected · ${BASIS[state.basis]} · ${methodLabel()} · ${rangeLabel()}${state.display==='levels'?' · '+baseLabel():''}`;
    root.querySelectorAll('[data-eer-enlarge],[data-eer-svg]').forEach(button=>button.disabled=false);
    root.querySelectorAll('[data-eer-range]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.eerRange===start+','+end)));
    configureCharts();
    state.charts.clear();
    for(const id of CHART_IDS){
      const config=state.configs.get(id);
      $('eer-unit-'+id).textContent=config.unit;
      // Quarto can normalize figure captions and remove their original IDs.
      const caption=root.querySelector(`[data-eer-panel="${id}"] figcaption`)||$('eer-caption-'+id);
      if(caption)caption.textContent=config.caption;
      const legend=$('eer-legend-'+id);if(legend)legend.innerHTML=legendHTML(config.legend);
      const heading=root.querySelector(`[data-eer-panel="${id}"] h3`);if(heading)heading.textContent=config.title;
      renderChart(id);
    }
    renderTable();
    if($('eer-dialog').open&&state.dialogChart)renderDialog();
    const year=state.years.includes(state.inspectYear)?state.inspectYear:state.years.find(value=>value>=state.inspectYear)||state.years.at(-1);
    inspectYear(year);
    window.EER_EXPLORER={ready:true,rowCount:state.rows.length,totalRows:state.data.series.length,chartCount:CHART_IDS.length,basis:state.basis,method:state.method,measure:state.measure,display:state.display,baseYear:state.base,range:[start,end],selectedYear:state.inspectYear,smoothing:state.display==='levels'&&$('eer-smooth').checked};
  }
  function renderDialog() {
    if(!state.dialogChart)return;
    const config=state.configs.get(state.dialogChart);
    $('eer-dialog-title').textContent=config.title;$('eer-dialog-subtitle').textContent=`${config.unit} · ${rangeLabel()}`;
    $('eer-dialog-caption').textContent=config.caption;$('eer-dialog-legend').innerHTML=legendHTML(config.legend);
    renderChart(state.dialogChart,$('eer-dialog-chart'),true);
    $('eer-dialog-readout').textContent=inspectionText(state.dialogChart);
  }
  function openDialog(id,trigger) {
    if(!state.valid)return;
    state.dialogChart=id;state.dialogTrigger=trigger;
    $('eer-dialog').showModal();renderDialog();inspectYear(state.inspectYear);
    $('eer-dialog-close').focus();
  }
  function download(filename,content,type) {
    const url=URL.createObjectURL(new Blob([content],{type})),anchor=document.createElement('a');
    anchor.href=url;anchor.download=filename;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);
  }
  function csvValue(value) {
    if(value===undefined||value===null)return '';
    const string=String(value);return /[",\n\r]/.test(string)?'"'+string.replaceAll('"','""')+'"':string;
  }
  function downloadCSV() {
    if(!state.valid)return;
    const headers=['year','trade_basis','method','reference_year','sample','neer_index','reer_index','relative_price_index','neer_yoy_pct','reer_yoy_pct','neer_log_change','reer_log_change','relative_price_log_change','neer_ma3_index','reer_ma3_index','neer_original_1929_100','reer_original_1929_100','relative_price_change_interpretation'];
    const records=state.rows.map(row=>[row.year,state.basis,state.method,state.base,row.sample,row.neer_level,row.reer_level,row.price_level,row.neer_yoy_pct,row.reer_yoy_pct,row.neer_log_change,row.reer_log_change,row.relative_price_log_change,row.neer_average,row.reer_average,row.neer,row.reer,state.method==='direct_current'?'ratio change includes changing weights':'chained relative-price log change']);
    const csv=[headers,...records].map(row=>row.map(csvValue).join(',')).join('\r\n')+'\r\n';
    download(`czechoslovakia-eer_${state.basis}_${state.method}_${rangeLabel()}_base-${state.base}.csv`,csv,'text/csv;charset=utf-8');
  }
  function wrap(value,maxChars) {
    const words=String(value).split(/\s+/),lines=[];let current='';
    for(const word of words){if(current&&current.length+word.length+1>maxChars){lines.push(current);current=word;}else current+=(current?' ':'')+word;}
    if(current)lines.push(current);return lines;
  }
  function exportSVG(id) {
    if(!state.valid)return;
    const config=state.configs.get(id),host=document.createElement('div');
    host.id='eer-export-temp';host.className='eer-chart';host.style.cssText='position:fixed;left:-12000px;top:0;width:1000px;';root.append(host);
    renderChart(id,host,true);
    const figure=host.querySelector('svg');
    if(!figure){host.remove();return;}
    const box=figure.getAttribute('viewBox').split(/\s+/).map(Number),width=box[2],plotHeight=box[3],headerHeight=95;
    const footerLines=wrap(config.caption,Math.floor((width-52)/6.4));
    const sourceLines=wrap('Source: Adam Dittrich, Czechoslovakia EER, 1920–1938. Reader edition: 22 October 2026. Annual analysis extension: '+(state.data.release_date||'2026-11-13')+'. https://adamdittrich.github.io/czechoslovakia-eer.html',Math.floor((width-52)/6.1));
    const footerHeight=24+footerLines.length*16+sourceLines.length*15+15,height=headerHeight+plotHeight+footerHeight;
    const svg=el('svg',{xmlns:NS,viewBox:`0 0 ${width} ${height}`,width,height,role:'img','aria-label':config.title});
    svg.append(el('title',{},config.title));svg.append(el('desc',{},config.caption));
    svg.append(el('rect',{width,height,fill:'#fff'}));
    text(svg,26,29,config.title,{'font-size':22,fill:'#163441','font-family':'Georgia,serif'});
    text(svg,26,51,`${config.unit} · ${rangeLabel()}`,{'font-size':12});
    let legendX=26,legendY=74;
    for(const item of config.legend){
      const itemWidth=item.label.length*6.2+35;
      if(legendX+itemWidth>width-24){legendX=26;legendY+=16;}
      if(item.type==='band'||item.type==='square')svg.append(el('rect',{x:legendX,y:legendY-8,width:17,height:9,fill:item.color,'fill-opacity':item.type==='band'?.45:1}));
      else line(svg,legendX,legendY-4,legendX+20,legendY-4,{stroke:item.color,'stroke-width':2.5,'stroke-dasharray':item.dash?'4 3':undefined});
      text(svg,legendX+25,legendY,item.label,{'font-size':11});legendX+=itemWidth;
    }
    const nested=figure.cloneNode(true);nested.setAttribute('x','0');nested.setAttribute('y',String(headerHeight));nested.removeAttribute('tabindex');svg.append(nested);
    let y=headerHeight+plotHeight+20;
    footerLines.forEach(value=>{text(svg,26,y,value,{'font-size':12});y+=16;});y+=9;
    sourceLines.forEach(value=>{text(svg,26,y,value,{'font-size':11,fill:'#6a777e'});y+=15;});
    const xml='<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(svg);
    host.remove();state.charts.delete('eer-export-temp');
    const exportedMethod=['decomposition','tradebasis'].includes(id)?chainMethod():state.method;
    download(`czechoslovakia-eer_${id}_${state.basis}_${exportedMethod}_${rangeLabel()}_base-${state.base}.svg`,xml,'image/svg+xml;charset=utf-8');
  }
  function setup(data) {
    if(!Array.isArray(data.series)||!Array.isArray(data.weights)||!Array.isArray(data.coverage)||!Array.isArray(data.years)||!Array.isArray(data.partners))throw new Error('The annual data file has an unsupported structure.');
    state.data=data;
    for(const row of data.series){const key=`${row.basis}|${row.method}`;if(!state.lookup.has(key))state.lookup.set(key,[]);state.lookup.get(key).push(row);}
    for(const rows of state.lookup.values())rows.sort((a,b)=>a.year-b.year);
    const referenceYears=data.years.filter(year=>year>=1925&&sourceRow(year,'TWEER','paasche')?.reer>0);
    $('eer-base').innerHTML=referenceYears.map(year=>`<option value="${year}"${year===1929?' selected':''}>${year}</option>`).join('');
    state.ready=true;$('eer-controls').disabled=false;
    root.querySelectorAll('#eer-controls input,#eer-controls select').forEach(control=>control.addEventListener('change',renderAll));
    for(const id of ['eer-start','eer-end']) $(id).addEventListener('input',renderAll);
    root.querySelectorAll('[data-eer-range]').forEach(button=>button.addEventListener('click',()=>{const [start,end]=button.dataset.eerRange.split(',');$('eer-start').value=start;$('eer-end').value=end;renderAll();}));
    root.querySelectorAll('[data-eer-enlarge]').forEach(button=>button.addEventListener('click',()=>openDialog(button.dataset.eerEnlarge,button)));
    root.querySelectorAll('[data-eer-svg]').forEach(button=>button.addEventListener('click',()=>exportSVG(button.dataset.eerSvg)));
    $('eer-year').addEventListener('input',()=>inspectYear(state.years[Number($('eer-year').value)]));
    $('eer-download-csv').addEventListener('click',downloadCSV);
    $('eer-dialog-close').addEventListener('click',()=>$('eer-dialog').close());
    $('eer-dialog-svg').addEventListener('click',()=>exportSVG(state.dialogChart));
    $('eer-dialog').addEventListener('close',()=>{state.dialogChart=null;state.charts.delete('eer-dialog-chart');state.dialogTrigger?.focus();});
    $('eer-dialog').addEventListener('click',event=>{if(event.target!==$('eer-dialog'))return;const rect=$('eer-dialog').getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)$('eer-dialog').close();});
    let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(renderAll,120);});
    renderAll();
  }
  fetch(root.dataset.source,{credentials:'same-origin'}).then(response=>{if(!response.ok)throw new Error('The annual data could not be loaded.');return response.json();}).then(setup).catch(error=>{
    $('eer-status').textContent='The interactive data could not be loaded. The static figures and downloads remain available below.';
    $('eer-range-error').hidden=false;$('eer-range-error').textContent=error.message;
    window.EER_EXPLORER={ready:false,error:error.message};
  });
})();
