/* Monthly Czechoslovak trade explorer. Trends are precomputed on the full sample. */
(() => {
  'use strict';
  const root = document.getElementById('monthly-explorer');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = {exports:'#1f77b4', imports:'#ff7f0e', balance:'#2ca02c', deficit:'#d62728', coverage:'#9467bd', turnover:'#317e87'};
  const METHODS = {
    raw: {label:'Observed monthly values', note:'The supplied monthly observations, with no additional smoothing.'},
    trailing3: {label:'3-month trailing average', note:'Each value averages the current month and the previous two months. Complete windows are required; the first two months are unavailable. Trailing averages place the window at its final month and therefore lag turning points.'},
    trailing6: {label:'6-month trailing average', note:'Each value averages the current month and the previous five months. Complete windows are required; the first five months are unavailable. Trailing averages place the window at its final month and therefore lag turning points.'},
    trailing12: {label:'12-month trailing average', note:'Each value averages the current month and the previous eleven months. Complete windows are required; the first eleven months are unavailable. The coverage ratio compares exports with imports over the same twelve months. This trailing average lags turning points.'},
    centered12: {label:'Centered 12-month average (2 × 12)', note:'The properly centered 2 × 12-month average uses six months on each side, with half weights on the two outer months. Six months at each end are unavailable. It uses later observations and aligns the smooth series with the month being shown.'},
    hp129600: {label:'HP trend (λ = 129,600)', note:'The Hodrick–Prescott trend uses λ = 129,600 and the full available sample in levels. It is a two-sided descriptive trend; estimates near sample boundaries and abrupt breaks are sensitive. Changing the displayed dates does not refit the trend.'}
  };
  const KEYS = ['exports_million_kc','imports_million_kc','trade_balance_million_kc','total_trade_million_kc','export_import_ratio_pct','normalized_balance_pct'];
  const CHARTS = {
    flows: {title:'Exports and imports', unit:'Million current Kč', zero:true, series:[{key:KEYS[0],label:'Exports',color:COLORS.exports},{key:KEYS[1],label:'Imports',color:COLORS.imports,dash:'7 4'}]},
    balance: {title:'Trade balance', unit:'Million current Kč', baseline:0, signed:true, series:[{key:KEYS[2],label:'Trade balance',color:COLORS.balance}], note:'Exports − imports. Positive = surplus; negative = deficit.'},
    coverage: {title:'Export coverage of imports', unit:'Percent', baseline:100, series:[{key:KEYS[4],label:'Export coverage',color:COLORS.coverage}], note:'100 × exports / imports. 100% = balanced trade.'},
    normalized: {title:'Balance relative to total trade', unit:'Percent', baseline:0, signed:true, series:[{key:KEYS[5],label:'Balance / total trade',color:COLORS.balance}], note:'100 × (exports − imports) / (exports + imports).'},
    turnover: {title:'Total trade', unit:'Million current Kč', zero:true, series:[{key:KEYS[3],label:'Total trade',color:COLORS.turnover}], note:'Exports + imports.'}
  };
  const READOUT = [
    {key:KEYS[0],label:'Exports',suffix:''}, {key:KEYS[1],label:'Imports',suffix:''},
    {key:KEYS[2],label:'Trade balance',suffix:'',signed:true},
    {key:KEYS[4],label:'Export coverage',suffix:'%'},
    {key:KEYS[5],label:'Balance / total trade',suffix:'%',signed:true},
    {key:KEYS[3],label:'Total trade',suffix:''}
  ];
  const state = {data:null, byMethod:new Map(), rawMap:new Map(), rows:[], raw:[], method:'trailing12', inspectDate:'1929-12-01', inspectIndex:0, charts:new Map(), dialogChart:null, valid:false, ready:false};
  window.FOREIGN_TRADE_EXPLORER = {ready:false, method:state.method, rowCount:0};
  const valid = value => typeof value === 'number' && Number.isFinite(value);
  const fmt = (value, digits=1) => valid(value) ? new Intl.NumberFormat('en-GB',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value) : '—';
  const valueLabel = (value, item) => (valid(value) && item.signed && value>0?'+':'') + fmt(value) + (valid(value)?item.suffix||'':'');
  const monthName = date => new Intl.DateTimeFormat('en-GB',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(date+'T12:00:00Z'));
  const monthShort = date => new Intl.DateTimeFormat('en-GB',{month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(date+'T12:00:00Z'));
  const monthNumber = date => Number(date.slice(0,4))*12+Number(date.slice(5,7))-1;
  const esc = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function svgEl(tag, attrs={}, content) {
    const element=document.createElementNS(NS,tag);
    for (const [key,value] of Object.entries(attrs)) if (value!==undefined) element.setAttribute(key,String(value));
    if (content!==undefined) element.textContent=content;
    return element;
  }
  function text(svg,x,y,label,attrs={}) {
    svg.append(svgEl('text',{x,y,fill:'#53636a','font-family':'Segoe UI,Arial,sans-serif','font-size':11,...attrs},label));
  }
  function line(svg,x1,y1,x2,y2,attrs={}) {
    svg.append(svgEl('line',{x1,y1,x2,y2,stroke:'#e6e2d9','stroke-width':1,...attrs}));
  }
  function niceScale(min,max,zero=false) {
    if (zero) { min=Math.min(0,min); max=Math.max(0,max); }
    if (min===max) { const d=Math.abs(min)*.08||1; min-=d; max+=d; }
    const padding=(max-min)*.06;
    if (!zero || min<0) min-=padding;
    max+=padding;
    const raw=(max-min)/4.5, exponent=10**Math.floor(Math.log10(raw)), fraction=raw/exponent;
    const step=(fraction<=1?1:fraction<=2?2:fraction<=2.5?2.5:fraction<=5?5:10)*exponent;
    const low=Math.floor(min/step)*step, high=Math.ceil(max/step)*step, values=[];
    for(let v=low;v<=high+step*.001;v+=step) values.push(Math.abs(v)<step*.0001?0:v);
    return {low,high,values,step};
  }
  function tickLabel(v,step) {
    if (Math.abs(v)>=1000) return fmt(v/1000,step<1000 && v%1000 ? 1:0)+'k';
    return fmt(v,step<1?Math.min(2,Math.ceil(-Math.log10(step))):v%1?1:0);
  }
  function dateTicks(rows,width) {
    const maxLabels=width<400?4:width<650?6:9;
    const first=monthNumber(rows[0].date), last=monthNumber(rows.at(-1).date), span=last-first;
    if (!span) return [{value:first,label:monthShort(rows[0].date)}];
    const step=span<=10?Math.max(1,Math.ceil(span/(maxLabels-1))):span<=36?Math.max(3,Math.ceil(span/(maxLabels-1)/3)*3):Math.max(12,Math.ceil(span/(maxLabels-1)/12)*12);
    const result=[];
    for (let n=Math.ceil(first/step)*step;n<=last;n+=step) {
      const year=Math.floor(n/12), month=n%12;
      const date=`${year}-${String(month+1).padStart(2,'0')}-01`;
      result.push({value:n,label:step>=12?String(year):monthShort(date)});
    }
    if (result.length<2) return [{value:first,label:monthShort(rows[0].date)},{value:last,label:monthShort(rows.at(-1).date)}];
    return result;
  }
  function methodLabel() { return METHODS[state.method].label; }
  function rangeLabel() { return state.rows.length ? `${monthShort(state.rows[0].date)}–${monthShort(state.rows.at(-1).date)}` : ''; }
  function showRaw() { return state.method!=='raw' && $('ft-observed').checked; }
  function pathData(rows,key,X,Y) {
    let path='', active=false;
    for (const row of rows) {
      if (!valid(row[key])) { active=false; continue; }
      path+=(active?' L':' M')+X(monthNumber(row.date)).toFixed(2)+' '+Y(row[key]).toFixed(2);
      active=true;
    }
    return path;
  }
  function chartEmpty(host, message) {
    host.replaceChildren();
    const width=Math.max(240,Math.round(host.clientWidth||600));
    const svg=svgEl('svg',{viewBox:`0 0 ${width} 220`,width,height:220,role:'img','aria-label':message});
    text(svg,width/2,100,'No complete values in this date range.',{'text-anchor':'middle','font-size':width<350?11:13});
    text(svg,width/2,124,'Choose another range or smoothing method.',{'text-anchor':'middle','font-size':width<350?10:12});
    host.append(svg);
    return svg;
  }
  function renderChart(id, hostId='ft-chart-'+id, enlarged=false) {
    const host=$(hostId), config=CHARTS[id], rows=state.rows;
    const selectedValues=rows.flatMap(row=>config.series.map(series=>row[series.key])).filter(valid);
    state.charts.delete(hostId);
    if (!rows.length || !selectedValues.length) {
      chartEmpty(host,'No complete values in the selected date range. Choose another range or smoothing method.');
      return;
    }
    host.replaceChildren();
    const width=Math.max(240,Math.round(host.clientWidth||600));
    const height=enlarged ? Math.min(540,Math.max(300,Math.round(window.innerHeight*.52))) : id==='flows' ? width<500?290:360 : width<400?255:280;
    const margin={left:width<350?43:53,right:15,top:27,bottom:35};
    const svg=svgEl('svg',{xmlns:NS,viewBox:`0 0 ${width} ${height}`,width,height,role:'img',tabindex:0,'aria-label':`${config.title}. ${methodLabel()}. ${rangeLabel()}. ${config.unit}. Use arrow keys to inspect months.`});
    svg.append(svgEl('title',{},`${config.title} — ${methodLabel()}`));
    svg.append(svgEl('desc',{},`${rangeLabel()}. ${config.unit}. ${config.note||'Exports shown in blue; imports in orange with a dashed line.'} ${showRaw()?'Faint lines show observed values.':''} The table below provides numeric values.`));
    const values=[...selectedValues];
    if (showRaw()) values.push(...state.raw.flatMap(row=>config.series.map(series=>row[series.key])).filter(valid));
    if (config.baseline!==undefined) values.push(config.baseline);
    const scale=niceScale(Math.min(...values),Math.max(...values),config.zero);
    const first=monthNumber(rows[0].date), last=monthNumber(rows.at(-1).date);
    const X=n=>first===last?(margin.left+width-margin.right)/2:margin.left+(n-first)/(last-first)*(width-margin.left-margin.right);
    const Y=value=>height-margin.bottom-(value-scale.low)/(scale.high-scale.low)*(height-margin.top-margin.bottom);
    text(svg,margin.left,14,config.unit==='Percent'?'%':'Million current Kč',{'font-size':10});
    for(const value of scale.values) {
      line(svg,margin.left,Y(value),width-margin.right,Y(value));
      text(svg,margin.left-7,Y(value)+3.5,tickLabel(value,scale.step),{'text-anchor':'end','font-size':10});
    }
    for(const tick of dateTicks(rows,width)) {
      line(svg,X(tick.value),height-margin.bottom,X(tick.value),height-margin.bottom+5,{stroke:'#a9a89f'});
      text(svg,X(tick.value),height-12,tick.label,{'text-anchor':'middle','font-size':width<400?9:10});
    }
    if (config.baseline!==undefined) line(svg,margin.left,Y(config.baseline),width-margin.right,Y(config.baseline),{stroke:'#7c807c','stroke-width':1.2,'stroke-dasharray':'4 4'});
    if (config.signed) {
      const clipId=hostId+'-negative';
      const defs=svgEl('defs'), clip=svgEl('clipPath',{id:clipId});
      clip.append(svgEl('rect',{x:margin.left,y:Y(0),width:width-margin.left-margin.right,height:Math.max(0,height-margin.bottom-Y(0))}));
      defs.append(clip);svg.append(defs);
    }
    for (const series of config.series) {
      if (showRaw()) svg.append(svgEl('path',{d:pathData(state.raw,series.key,X,Y),fill:'none',stroke:series.color,'stroke-width':1.2,'stroke-opacity':.25,'stroke-dasharray':series.dash||undefined,'stroke-linecap':'round','stroke-linejoin':'round'}));
      const path=pathData(rows,series.key,X,Y);
      svg.append(svgEl('path',{d:path,fill:'none',stroke:series.color,'stroke-width':2.5,'stroke-dasharray':series.dash||undefined,'stroke-linecap':'round','stroke-linejoin':'round'}));
      if(config.signed) svg.append(svgEl('path',{d:path,fill:'none',stroke:COLORS.deficit,'stroke-width':2.5,'clip-path':`url(#${hostId}-negative)`,'stroke-linecap':'round','stroke-linejoin':'round'}));
      if(rows.length===1 && valid(rows[0][series.key])) svg.append(svgEl('circle',{cx:X(first),cy:Y(rows[0][series.key]),r:3.5,fill:series.color}));
    }
    const marker=svgEl('g',{'data-ft-marker':'true','pointer-events':'none'});
    svg.append(marker);
    const info={svg,marker,X,Y,config,rows,width,height,margin};
    state.charts.set(hostId,info);
    const inspectPointer=event=>{
      const rect=svg.getBoundingClientRect();
      const px=(event.clientX-rect.left)*width/rect.width;
      if (px<margin.left || px>width-margin.right) return;
      const month=first+(px-margin.left)/(width-margin.left-margin.right)*(last-first);
      let index=Math.round(month-first);
      index=Math.max(0,Math.min(rows.length-1,index));
      if (index!==state.inspectIndex) inspectMonth(index);
    };
    svg.addEventListener('pointermove',event=>{if(event.pointerType!=='touch')inspectPointer(event);});
    svg.addEventListener('pointerdown',inspectPointer);
    svg.addEventListener('keydown',event=>{
      let index=state.inspectIndex;
      if (event.key==='ArrowLeft') index--;
      else if(event.key==='ArrowRight') index++;
      else if(event.key==='Home') index=0;
      else if(event.key==='End') index=rows.length-1;
      else return;
      event.preventDefault(); inspectMonth(Math.max(0,Math.min(rows.length-1,index)));
    });
    host.append(svg);
  }
  function inspectMonth(index) {
    if(!state.rows.length) return;
    state.inspectIndex=index;
    const row=state.rows[index], raw=state.rawMap.get(row.date);
    state.inspectDate=row.date;
    $('ft-month').value=String(index);
    $('ft-month').setAttribute('aria-valuetext',monthName(row.date));
    $('ft-selected-month').textContent=monthName(row.date);
    $('ft-readout').innerHTML=READOUT.map(item=>`<div><dt>${item.label}${item.suffix?'':' (million Kč)'}</dt><dd>${valueLabel(row[item.key],item)}${state.method!=='raw'?`<small>Observed: ${valueLabel(raw?.[item.key],item)}</small>`:''}</dd></div>`).join('');
    for(const chart of state.charts.values()) {
      chart.marker.replaceChildren();
      const x=chart.X(monthNumber(row.date));
      line(chart.marker,x,chart.margin.top,x,chart.height-chart.margin.bottom,{stroke:'#9b9289','stroke-dasharray':'3 3'});
      for(const series of chart.config.series) if(valid(row[series.key])) {
        const color=chart.config.signed && row[series.key]<0?COLORS.deficit:series.color;
        chart.marker.append(svgEl('circle',{cx:x,cy:chart.Y(row[series.key]),r:4,fill:'#fff',stroke:color,'stroke-width':2}));
      }
    }
    root.querySelectorAll('#ft-table-body tr[aria-current]').forEach(element=>element.removeAttribute('aria-current'));
    $('ft-row-'+row.date)?.setAttribute('aria-current','true');
    if(state.dialogChart) {
      const config=CHARTS[state.dialogChart];
      $('ft-dialog-readout').textContent=monthName(row.date)+' · '+config.series.map(series=>`${series.label}: ${fmt(row[series.key])}${config.unit==='Percent'?'%':' million Kč'}`).join(' · ');
    }
    window.FOREIGN_TRADE_EXPLORER.selectedMonth=row.date;
  }
  function renderTable() {
    $('ft-table-caption').textContent=`${methodLabel()} · ${rangeLabel()}`;
    $('ft-table-note').textContent='Trade values are in million current Kč. Ratios are percentage numbers. A dash denotes an unavailable value. The CSV also includes the observed values for comparison.';
    const keys=[KEYS[0],KEYS[1],KEYS[2],KEYS[4],KEYS[5],KEYS[3]];
    $('ft-table-body').innerHTML=state.rows.map(row=>`<tr id="ft-row-${row.date}"><th scope="row">${monthShort(row.date)}</th>${keys.map(key=>`<td class="num">${fmt(row[key],2)}</td>`).join('')}</tr>`).join('');
  }
  function invalidate(message) {
    state.valid=false;state.rows=[];state.raw=[];state.charts.clear();
    $('ft-range-error').hidden=false;$('ft-range-error').textContent=message;
    $('ft-download-csv').disabled=true;
    root.querySelectorAll('[data-ft-enlarge],[data-ft-svg]').forEach(button=>button.disabled=true);
    for(const id of Object.keys(CHARTS)) chartEmpty($('ft-chart-'+id),message);
    $('ft-table-body').replaceChildren();$('ft-readout').replaceChildren();$('ft-selected-month').textContent='Choose a valid date range';$('ft-month').disabled=true;
    window.FOREIGN_TRADE_EXPLORER.rowCount=0;
  }
  function renderAll() {
    if(!state.ready) return;
    const start=$('ft-start').value, end=$('ft-end').value;
    if(!start || !end || !$('ft-start').checkValidity() || !$('ft-end').checkValidity()) return invalidate('Choose dates between January 1924 and December 1938.');
    if(start>end) return invalidate('The starting month must be before or equal to the ending month.');
    state.method=$('ft-method').value;
    state.rows=state.byMethod.get(state.method).filter(row=>row.date.slice(0,7)>=start && row.date.slice(0,7)<=end);
    state.raw=state.rows.map(row=>state.rawMap.get(row.date));
    if(!state.rows.length) return invalidate('No observations are available in this date range.');
    state.valid=true;
    $('ft-range-error').hidden=true;
    $('ft-observed').disabled=state.method==='raw';
    $('ft-method-note').textContent=METHODS[state.method].note;
    $('ft-readout-note').textContent=state.method==='raw'?'The values below are the observed monthly values.':'The larger values show the selected method; observed monthly values appear underneath. A dash means the smoothing window is unavailable.';
    $('ft-download-csv').disabled=false;$('ft-month').disabled=state.rows.length===1;
    root.querySelectorAll('[data-ft-enlarge],[data-ft-svg]').forEach(button=>button.disabled=false);
    root.querySelectorAll('.ft-raw-key').forEach(element=>element.hidden=!showRaw());
    root.querySelectorAll('[data-ft-range]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.ftRange===start+','+end)));
    $('ft-month').max=String(state.rows.length-1);
    const index=state.rows.findIndex(row=>row.date>=state.inspectDate);
    state.inspectIndex=index<0?state.rows.length-1:index;
    for(const id of Object.keys(CHARTS)) renderChart(id);
    renderTable();
    if($('ft-dialog').open && state.dialogChart) renderDialog();
    inspectMonth(state.inspectIndex);
    window.FOREIGN_TRADE_EXPLORER={ready:true,method:state.method,rowCount:state.rows.length,totalRows:state.data.rows.length,selectedMonth:state.inspectDate,range:[start,end],chartCount:5};
  }
  function download(filename,content,type) {
    const url=URL.createObjectURL(new Blob([content],{type}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download=filename;document.body.append(anchor);anchor.click();anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function csvValue(value) {
    if(value===null || value===undefined) return '';
    const string=String(value);return /[",\n\r]/.test(string)?'"'+string.replaceAll('"','""')+'"':string;
  }
  function downloadCSV() {
    if(!state.valid) return;
    const header=['date','method',...KEYS,...KEYS.map(key=>'observed_'+key)];
    const rows=state.rows.map(row=>[row.date,state.method,...KEYS.map(key=>row[key]),...KEYS.map(key=>state.rawMap.get(row.date)?.[key])]);
    const csv=[header,...rows].map(row=>row.map(csvValue).join(',')).join('\r\n')+'\r\n';
    download(`czechoslovak-trade_${state.method}_${$('ft-start').value}_${$('ft-end').value}.csv`,csv,'text/csv;charset=utf-8');
  }
  function wrapText(value,maxCharacters) {
    const lines=[];let current='';
    for(const word of value.split(/\s+/)) {
      if(current && current.length+word.length+1>maxCharacters) { lines.push(current);current=word; }
      else current+=(current?' ':'')+word;
    }
    if(current) lines.push(current);
    return lines;
  }
  function exportSVG(id) {
    if(!state.valid) return;
    const config=CHARTS[id];
    const source=state.dialogChart===id && $('ft-dialog').open ? $('ft-dialog-chart').querySelector('svg') : $('ft-chart-'+id).querySelector('svg');
    if(!source) return;
    const width=source.viewBox.baseVal.width, chartHeight=source.viewBox.baseVal.height;
    const svg=svgEl('svg',{xmlns:NS,width,role:'img','aria-label':`${config.title}. ${methodLabel()}. ${rangeLabel()}.`});
    svg.append(svgEl('title',{},`${config.title} — ${methodLabel()}`));
    let y=23;
    const addWrapped=(value,size=12,color='#53636a')=>{
      for(const ln of wrapText(value,Math.max(22,Math.floor((width-24)/(size*.55))))) {
        text(svg,12,y,ln,{'font-size':size,fill:color});y+=size+5;
      }
    };
    addWrapped(config.title,16,'#162b36');
    addWrapped(`${methodLabel()} · ${rangeLabel()}`,11);
    addWrapped(config.unit+(config.note?' · '+config.note:''),10);
    let x=12;
    for(const series of config.series) {
      const need=series.label.length*6+42;
      if(x+need>width-12 && x>12) {x=12;y+=18;}
      line(svg,x,y-4,x+22,y-4,{stroke:series.color,'stroke-width':2.5,'stroke-dasharray':series.dash||undefined});
      text(svg,x+29,y,series.label,{'font-size':10});x+=need;
    }
    y+=18;
    if(showRaw()) {addWrapped('Faint lines: observed monthly values.',10);y+=3;}
    const chartGroup=svgEl('g',{transform:`translate(0,${y})`});
    for(const child of source.children) if(!child.hasAttribute('data-ft-marker') && !['title','desc'].includes(child.tagName)) chartGroup.append(child.cloneNode(true));
    svg.append(chartGroup);y+=chartHeight+17;
    addWrapped('Source: Adam Dittrich, Czechoslovak Foreign Trade: Interwar Dataset. Monthly analysis updated 13 November 2026.',10);
    addWrapped('Current-price values. Smoothing is not deflation or formal seasonal adjustment.',10);
    addWrapped(METHODS[state.method].note,10);
    svg.setAttribute('height',String(y+10));svg.setAttribute('viewBox',`0 0 ${width} ${y+10}`);
    svg.insertBefore(svgEl('rect',{width,height:y+10,fill:'#fff'}),svg.firstChild);
    download(`czechoslovak-trade_${id}_${state.method}_${$('ft-start').value}_${$('ft-end').value}.svg`,new XMLSerializer().serializeToString(svg),'image/svg+xml;charset=utf-8');
  }
  function renderDialog() {
    const config=CHARTS[state.dialogChart];
    $('ft-dialog-title').textContent=config.title;
    $('ft-dialog-method').textContent=`${methodLabel()} · ${rangeLabel()} · ${config.unit}`;
    $('ft-dialog-legend').innerHTML=config.series.map(series=>`<span><i ${series.dash?'class="ft-dashed" ':''}style="--ft-color:${series.color}"></i>${esc(series.label)}</span>`).join('')+(showRaw()?'<span>Faint lines: observed values</span>':'');
    $('ft-dialog-note').textContent=(config.note||'Exports are shown in blue; imports in orange with a dashed line.')+' '+METHODS[state.method].note;
    renderChart(state.dialogChart,'ft-dialog-chart',true);
    inspectMonth(state.inspectIndex);
  }
  let dialogTrigger=null;
  function openDialog(id,trigger) {
    if(!state.valid) return;
    state.dialogChart=id;dialogTrigger=trigger;
    $('ft-dialog').showModal();renderDialog();
  }
  function bindControls() {
    for(const id of ['ft-method','ft-start','ft-end','ft-observed']) $(id).addEventListener('change',renderAll);
    $('ft-month').addEventListener('input',()=>inspectMonth(Number($('ft-month').value)));
    $('ft-download-csv').addEventListener('click',downloadCSV);
    root.querySelectorAll('[data-ft-range]').forEach(button=>button.addEventListener('click',()=>{
      const [start,end]=button.dataset.ftRange.split(',');$('ft-start').value=start;$('ft-end').value=end;renderAll();
    }));
    root.querySelectorAll('[data-ft-enlarge]').forEach(button=>button.addEventListener('click',()=>openDialog(button.dataset.ftEnlarge,button)));
    root.querySelectorAll('[data-ft-svg]').forEach(button=>button.addEventListener('click',()=>exportSVG(button.dataset.ftSvg)));
    $('ft-dialog-close').addEventListener('click',()=>$('ft-dialog').close());
    $('ft-dialog-svg').addEventListener('click',()=>exportSVG(state.dialogChart));
    $('ft-dialog').addEventListener('close',()=>{state.charts.delete('ft-dialog-chart');state.dialogChart=null;dialogTrigger?.focus();});
    $('ft-dialog').addEventListener('click',event=>{
      if(event.target!==$('ft-dialog')) return;
      const rect=$('ft-dialog').getBoundingClientRect();
      if(event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom) $('ft-dialog').close();
    });
    let resizeTimer;
    window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(state.ready && state.valid)renderAll();},120);});
  }
  async function loadData() {
    $('ft-retry').hidden=true;$('ft-load-status').hidden=false;$('ft-load-status').textContent='Loading the monthly explorer…';
    try {
      const response=await fetch(root.dataset.source,{cache:'no-cache'});
      if(!response.ok) throw new Error(`Data request returned ${response.status}`);
      const data=await response.json();
      if(data.schema_version!==1 || !Array.isArray(data.rows)) throw new Error('Unrecognized data format');
      const groups=new Map(Object.keys(METHODS).map(id=>[id,[]]));
      for(const row of data.rows) {
        if(!groups.has(row.method) || !/^\d{4}-\d{2}-01$/.test(row.date) || KEYS.some(key=>row[key]!==null && !valid(row[key]))) throw new Error('Invalid monthly observation');
        groups.get(row.method).push(row);
      }
      for(const rows of groups.values()) {
        rows.sort((a,b)=>a.date.localeCompare(b.date));
        if(!rows.length || new Set(rows.map(row=>row.date)).size!==rows.length) throw new Error('Incomplete or duplicated method data');
      }
      const raw=groups.get('raw'),dates=raw.map(row=>row.date).join(',');
      for(const rows of groups.values()) if(rows.map(row=>row.date).join(',')!==dates) throw new Error('Method calendars do not agree');
      for(let i=1;i<raw.length;i++) if(monthNumber(raw[i].date)!==monthNumber(raw[i-1].date)+1) throw new Error('Monthly calendar is not regular');
      state.data=data;state.byMethod=groups;state.rawMap=new Map(raw.map(row=>[row.date,row]));
      $('ft-method').innerHTML=Object.entries(METHODS).map(([id,method])=>`<option value="${id}"${id===state.method?' selected':''}>${esc(method.label)}</option>`).join('');
      for(const id of ['ft-start','ft-end']) {$(id).min=raw[0].date.slice(0,7);$(id).max=raw.at(-1).date.slice(0,7);}
      $('ft-start').value=raw[0].date.slice(0,7);$('ft-end').value=raw.at(-1).date.slice(0,7);
      $('ft-content').hidden=false;$('ft-load-status').hidden=true;state.ready=true;renderAll();
    } catch(error) {
      $('ft-load-status').textContent='The interactive data could not be loaded. Try again, or use the downloadable data and figures below.';
      $('ft-retry').hidden=false;window.FOREIGN_TRADE_EXPLORER={ready:false,error:String(error.message)};
    }
  }
  $('ft-retry').addEventListener('click',loadData);
  bindControls();loadData();
})();
