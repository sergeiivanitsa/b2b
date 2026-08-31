import { CompanyPublicH2ContractError } from './contractErrors'
import { validateArbitrationPolicyV3 } from './arbitrationContractSemantics'
import { BLOCK_IDS, object, type CompanyPublicH2, type Obj } from './contractSchema'
import { isStrictJsonInteger, isStrictJsonObject, type StrictJsonValue } from './strictJson'

const BLOCK_ORDER=['hero_status','narrative','in_page_navigation','requisites','finance_f1_liquidity','finance_f2_funding','finance_f3_growth','finance_f4_profit_per_100','finance_f5_yearly_table','arbitration_a1_activity','arbitration_a2_roles','arbitration_a3_outcomes','arbitration_a4_case_amounts','arbitration_a5_opponents','sources_limitations','neutral_actions'] as const
const COVERAGE=['requisites','narrative','finance_f1','finance_f2','finance_f3','finance_f4','finance_f5','arbitration_a1','arbitration_a2','arbitration_a3','arbitration_a4','arbitration_a5','sources_limitations'] as const
const fail=(m:string):never=>{throw new CompanyPublicH2ContractError(m)}
const rec=(v:StrictJsonValue|undefined,p:string):Obj=>object(v,p)
const s=(v:StrictJsonValue|undefined,p:string):string=>typeof v==='string'?v:fail(p+' must be string')
const i=(v:StrictJsonValue|undefined,p:string):bigint=>{const item=isStrictJsonInteger(v)?v:fail(p+' must be integer');return item.value}
const ar=(v:StrictJsonValue|undefined,p:string):readonly StrictJsonValue[]=>Array.isArray(v)?v:fail(p+' must be array')
const same=(left:readonly unknown[],right:readonly unknown[])=>left.length===right.length&&left.every((value,index)=>value===right[index])
const unique=(items:readonly string[])=>new Set(items).size===items.length

type Dec=Readonly<{ coefficient:bigint; scale:bigint }>
function decimal(raw:string,p:string):Dec {
  if(!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$/.test(raw))fail(`${p} invalid decimal`)
  const negative=raw.startsWith('-'), body=negative?raw.slice(1):raw, [whole,fraction='']=body.split('.')
  return {coefficient:(negative?-1n:1n)*BigInt(`${whole}${fraction}`),scale:BigInt(fraction.length)}
}
function pow10(scale:bigint):bigint { let r=1n;for(let n=0n;n<scale;n+=1n)r*=10n;return r }
function cmp(a:Dec,b:Dec):number { const scale=a.scale>b.scale?a.scale:b.scale, x=a.coefficient*pow10(scale-a.scale),y=b.coefficient*pow10(scale-b.scale);return x===y?0:x<y?-1:1 }
function add(a:Dec,b:Dec):Dec { const scale=a.scale>b.scale?a.scale:b.scale;return {coefficient:a.coefficient*pow10(scale-a.scale)+b.coefficient*pow10(scale-b.scale),scale} }
function mul(a:Dec,b:bigint):Dec{return {coefficient:a.coefficient*b,scale:a.scale}}
function div(a:Dec,b:bigint):Dec{return {coefficient:a.coefficient,scale:a.scale+BigInt(b.toString().length-1)}}
function d(v:StrictJsonValue|undefined,p:string):Dec{return decimal(s(v,p),p)}
function money(v:StrictJsonValue|undefined,p:string):void {const x=rec(v,p), source=d(x.source_thousand_decimal,`${p}.source_thousand_decimal`),rub=d(x.rub_decimal,`${p}.rub_decimal`),million=d(x.million_decimal,`${p}.million_decimal`);if(cmp(rub,mul(source,1000n))!==0||cmp(million,div(source,1000n))!==0)fail(`${p} finance money units do not agree`);const [exact,compact]=moneyDisplays(source);if(s(x.display_exact,`${p}.display_exact`)!==exact||s(x.display_compact,`${p}.display_compact`)!==compact)fail(`${p} finance money display mismatch`)}
function axis(v:StrictJsonValue|undefined,p:string):void {const x=rec(v,p),a=d(x.axis_min_decimal,`${p}.axis_min_decimal`),b=d(x.axis_max_decimal,`${p}.axis_max_decimal`);if(cmp(a,{coefficient:0n,scale:0n})>0||cmp(b,{coefficient:0n,scale:0n})<0||cmp(a,b)>0)fail(`${p} axis must contain zero and be ordered`)}
function scope(v:StrictJsonValue|undefined,p:string):void {const x=rec(v,p);if(i(x.shown,`${p}.shown`) !== (i(x.eligible_total,`${p}.eligible_total`)<20n?i(x.eligible_total,`${p}.eligible_total`):20n))fail(`${p} invalid shown count`)}
function nfc(value:StrictJsonValue,path='root'):void {if(typeof value==='string'){if(value!==value.normalize('NFC')||[...value].some(c=>{const n=c.codePointAt(0)!;return n>=0xd800&&n<=0xdfff}))fail(`${path} must be NFC Unicode scalars`);return}if(Array.isArray(value)){value.forEach((x,n)=>nfc(x,`${path}[${n}]`));return}if(isStrictJsonObject(value)){for(const [k,x] of Object.entries(value)){if(k!==k.normalize('NFC'))fail(`${path} key must be NFC`);nfc(x,`${path}.${k}`)}}}
function detailScopes(value:StrictJsonValue,path='root'):void {if(Array.isArray(value)){value.forEach((x,n)=>detailScopes(x,`${path}[${n}]`));return}if(isStrictJsonObject(value)){if(Object.hasOwn(value,'population_scope')&&Object.hasOwn(value,'eligible_total')&&Object.hasOwn(value,'shown')&&Object.hasOwn(value,'cap')&&Object.hasOwn(value,'rows_received')&&Object.hasOwn(value,'source_total'))scope(value,path);Object.entries(value).forEach(([k,x])=>detailScopes(x,`${path}.${k}`))}}
function axes(value:StrictJsonValue,path='root'):void {if(Array.isArray(value)){value.forEach((x,n)=>axes(x,`${path}[${n}]`));return}if(isStrictJsonObject(value)){if(Object.hasOwn(value,'axis_min_decimal')&&Object.hasOwn(value,'axis_max_decimal'))axis(value,path);Object.entries(value).forEach(([k,x])=>axes(x,`${path}.${k}`))}}
function monies(value:StrictJsonValue,path='root'):void {if(Array.isArray(value)){value.forEach((x,n)=>monies(x,`${path}[${n}]`));return}if(isStrictJsonObject(value)){if(Object.hasOwn(value,'source_thousand_decimal')&&Object.hasOwn(value,'rub_decimal')&&Object.hasOwn(value,'million_decimal')&&Object.hasOwn(value,'unit_id'))money(value,path);Object.entries(value).forEach(([k,x])=>monies(x,`${path}.${k}`))}}
function zero():Dec{return {coefficient:0n,scale:0n}}
function neg(value:Dec):Dec{return {coefficient:-value.coefficient,scale:value.scale}}
function inAxis(value:Dec, raw:StrictJsonValue|undefined, path:string):void {const a=rec(raw,path), min=d(a.axis_min_decimal,`${path}.axis_min_decimal`),max=d(a.axis_max_decimal,`${path}.axis_max_decimal`);if(cmp(value,min)<0||cmp(value,max)>0)fail(`${path} geometry outside axis`)}
function intervalInAxis(raw:StrictJsonValue|undefined, axisRaw:StrictJsonValue|undefined, path:string):void {const item=rec(raw,path);inAxis(d(item.start_ratio_decimal,`${path}.start_ratio_decimal`),axisRaw,path);inAxis(d(item.end_ratio_decimal,`${path}.end_ratio_decimal`),axisRaw,path)}
function moneySource(raw:StrictJsonValue|undefined,path:string):Dec{return d(rec(raw,path).source_thousand_decimal,`${path}.source_thousand_decimal`)}

function abs(value:bigint):bigint{return value<0n?-value:value}
function sub(left:Dec,right:Dec):Dec{return add(left,neg(right))}
function minMax(values:readonly Dec[]):readonly [Dec,Dec]{let minimum=zero(),maximum=zero();for(const value of values){if(cmp(value,minimum)<0)minimum=value;if(cmp(value,maximum)>0)maximum=value}return [minimum,maximum]}
function axisPair(raw:StrictJsonValue|undefined,path:string):readonly [Dec,Dec]{const value=rec(raw,path);return [d(value.axis_min_decimal,`${path}.axis_min_decimal`),d(value.axis_max_decimal,`${path}.axis_max_decimal`)]}
function exactAxis(raw:StrictJsonValue|undefined,values:readonly Dec[],path:string):void{const actual=axisPair(raw,path),expected=minMax(values);if(cmp(actual[0],expected[0])!==0||cmp(actual[1],expected[1])!==0)fail(`${path} exact axis mismatch`)}
function exactInterval(raw:StrictJsonValue|undefined,start:Dec,end:Dec,path:string):void{const value=rec(raw,path);if(cmp(d(value.start_ratio_decimal,`${path}.start_ratio_decimal`),start)!==0||cmp(d(value.end_ratio_decimal,`${path}.end_ratio_decimal`),end)!==0)fail(`${path} interval mismatch`)}
function fraction(numerator:Dec,denominator:Dec,multiplier:bigint):Readonly<{numerator:bigint;denominator:bigint}>{let top=numerator.coefficient*multiplier*pow10(denominator.scale),bottom=denominator.coefficient*pow10(numerator.scale);if(bottom===0n)fail('decimal division by zero');if(bottom<0n){top=-top;bottom=-bottom}return {numerator:top,denominator:bottom}}
function quantizedRatio(numerator:Dec,denominator:Dec,multiplier=1n,scale=6n):Dec{const value=fraction(numerator,denominator,multiplier),factor=pow10(scale),scaled=value.numerator*factor;let coefficient=scaled/value.denominator;const remainder=scaled%value.denominator;if(abs(remainder)*2n>=value.denominator)coefficient+=scaled<0n?-1n:1n;return {coefficient,scale}}
function decimalText(value:Dec,fixedScale?:bigint):string{let coefficient=value.coefficient,scale=value.scale;if(fixedScale!==undefined){if(scale>fixedScale)fail('cannot widen fixed decimal');coefficient*=pow10(fixedScale-scale);scale=fixedScale}const negative=coefficient<0n,digits=abs(coefficient).toString().padStart(Number(scale)+1,'0'),split=digits.length-Number(scale),whole=digits.slice(0,split),fractionPart=scale===0n?'':digits.slice(split),rendered=fractionPart?`${whole}.${fractionPart}`:whole;return `${negative?'−':''}${rendered}`.replace('.',',')}
function canonicalDecimalText(value:Dec):string{let coefficient=value.coefficient,scale=value.scale;while(scale>0n&&coefficient%10n===0n){coefficient/=10n;scale-=1n}return decimalText({coefficient,scale})}
function moneyDisplays(source:Dec):readonly [string,string]{const million=div(source,1000n),exact=source.scale===0n?decimalText({coefficient:source.coefficient,scale:3n},3n):canonicalDecimalText(million),compact=canonicalDecimalText(quantizedRatio(source,{coefficient:1000n,scale:0n},1n,1n));return [`${exact} млн ₽`,`${compact} млн ₽`]}
function roundingError(numerator:Dec,denominator:Dec,rounded:Dec):Readonly<{numerator:bigint;denominator:bigint}>{const value=fraction(numerator,denominator,100n),factor=pow10(rounded.scale);return {numerator:abs(value.numerator*factor-rounded.coefficient*value.denominator),denominator:value.denominator}}
function derivedShares(equity:Dec,debt:Dec,denominator:Dec):readonly [Dec,Dec]{const shares:[Dec,Dec]=[quantizedRatio(equity,denominator,100n),quantizedRatio(debt,denominator,100n)],residual=100n*pow10(6n)-shares[0].coefficient-shares[1].coefficient,first=roundingError(equity,denominator,shares[0]),second=roundingError(debt,denominator,shares[1]),winner=first.numerator*second.denominator>=second.numerator*first.denominator?0:1;shares[winner]={coefficient:shares[winner].coefficient+residual,scale:6n};return shares}
function expectedYoy(previous:Dec|null,current:Dec|null):Dec|null{return previous===null||current===null||cmp(previous,zero())<=0?null:quantizedRatio(sub(current,previous),previous,100n)}
function exactNullableDecimal(raw:StrictJsonValue|undefined,expected:Dec|null,path:string):void{if((raw===null)!==(expected===null))fail(`${path} nullable decimal mismatch`);if(raw!==null&&expected!==null&&cmp(d(raw,path),expected)!==0)fail(`${path} decimal mismatch`)}

const F5_IDS=['2110','1600','1250','1240','1230','1210','1500','1300','2400'] as const
const F5_LABELS=['Продажи','Всё имущество','Деньги на счетах','Финансовые вложения','Долги покупателей','Запасы','Ближайшие обязательства','Свои средства','Чистая прибыль'] as const

function finance(root:Obj):void {
 const blocks=rec(root.blocks,'blocks')
 const f1=blocks.finance_f1
 if(f1!==null){
  const x=rec(f1,'finance_f1'),segments=ar(x.segments,'finance_f1.segments')
  if(!same(segments.map((z,n)=>s(rec(z,`finance_f1.segments[${n}]`).metric_id,'metric_id')),['1250','1240','1230','1500']))fail('F1 segments are fixed')
  const cash=moneySource(x.cash_1250,'finance_f1.cash_1250'),investments=moneySource(x.investments_1240,'finance_f1.investments_1240'),receivables=moneySource(x.receivables_1230,'finance_f1.receivables_1230'),short=moneySource(x.short_liabilities_1500,'finance_f1.short_liabilities_1500'),cashAndInvestments=add(cash,investments),available=add(cashAndInvestments,receivables),difference=sub(available,short),sourceValues=[cash,investments,receivables,short] as const
  if(cmp(available,moneySource(x.available_without_inventory,'finance_f1.available_without_inventory'))!==0||cmp(difference,moneySource(x.difference,'finance_f1.difference'))!==0)fail('F1 arithmetic mismatch')
  const expected:readonly (readonly [Dec,Dec])[]=[[zero(),cash],[cash,cashAndInvestments],[cashAndInvestments,available],[zero(),short]]
  segments.forEach((q,n)=>{const segment=rec(q,`finance_f1.segments[${n}]`),[start,end]=expected[n];if(cmp(moneySource(segment.value,`finance_f1.segments[${n}].value`),sourceValues[n])!==0)fail('F1 segment value mismatch');exactInterval(segment.geometry,start,end,`finance_f1.segments[${n}].geometry`);intervalInAxis(segment.geometry,x.axis,`finance_f1.segments[${n}].geometry`)})
  exactAxis(x.axis,[cash,investments,receivables,short,cashAndInvestments,available,difference],'finance_f1.axis')
 }
 const f2=blocks.finance_f2
 if(f2!==null){
  const x=rec(f2,'finance_f2'), anchor=i(x.anchor_year,'finance_f2.anchor_year'),start=i(x.window_start_year,'finance_f2.window_start_year')
  if(start!==anchor-6n||!same(ar(x.periods,'finance_f2.periods').map((q,n)=>i(rec(q,`finance_f2.periods[${n}]`).year,'year')),Array.from({length:7},(_,n)=>start+BigInt(n))))fail('F2 periods must be seven ascending years')
  ar(x.periods,'finance_f2.periods').forEach((q,n)=>{
   const p=rec(q,`finance_f2.periods[${n}]`),state=s(p.state,'state'),mode=s(p.mode,'mode'),moneyFields=['equity_1300','long_liabilities_1400','short_liabilities_1500','debt','denominator'],derived=[p.equity_share_decimal,p.debt_share_decimal,p.axis,...ar(p.geometry_by_metric,'geometry_by_metric')],allMoney=moneyFields.every(k=>p[k]!==null),anyMoney=moneyFields.some(k=>p[k]!==null),allDerived=derived.every(z=>z!==null),anyDerived=derived.some(z=>z!==null)
   if(state==='gap'&&(anyMoney||mode!=='unavailable'||anyDerived))fail('F2 gap cannot infer values')
   if(state==='denominator_unavailable'&&(!allMoney||mode!=='unavailable'||anyDerived))fail('F2 denominator shape mismatch')
   if(state==='available'&&(!allMoney||mode==='unavailable'||!allDerived))fail('F2 available shape mismatch')
   if(state!=='gap'){
    const equity=moneySource(p.equity_1300,'f2.equity'),long=moneySource(p.long_liabilities_1400,'f2.long'),short=moneySource(p.short_liabilities_1500,'f2.short'),debt=add(long,short),denominator=add(equity,debt)
    if(cmp(debt,moneySource(p.debt,'f2.debt'))!==0||cmp(denominator,moneySource(p.denominator,'f2.denominator'))!==0)fail('F2 arithmetic mismatch')
    if(state==='denominator_unavailable'){if(cmp(denominator,zero())>0)fail('F2 unavailable denominator must be non-positive');return}
    if(cmp(denominator,zero())<=0)fail('F2 available denominator must be positive')
    const shares=derivedShares(equity,debt,denominator),expectedMode=shares.some(value=>cmp(value,zero())<0)?'diverging_signed':'stacked_100',geometries=ar(p.geometry_by_metric,'f2.geometry')
    exactNullableDecimal(p.equity_share_decimal,shares[0],'f2.equity_share');exactNullableDecimal(p.debt_share_decimal,shares[1],'f2.debt_share')
    if(mode!==expectedMode)fail('F2 mode mismatch')
    if(expectedMode==='stacked_100'){
      exactAxis(p.axis,[{coefficient:100n,scale:0n}],'f2.axis');exactInterval(geometries[0],zero(),shares[0],`F2[${n}].geometry[0]`);exactInterval(geometries[1],shares[0],{coefficient:100n,scale:0n},`F2[${n}].geometry[1]`)
    }else{
      exactAxis(p.axis,shares,'f2.axis');exactInterval(geometries[0],zero(),shares[0],`F2[${n}].geometry[0]`);exactInterval(geometries[1],zero(),shares[1],`F2[${n}].geometry[1]`)
    }
    geometries.forEach((geometry,index)=>intervalInAxis(geometry,p.axis,`F2[${n}].geometry[${index}]`))
   }
  })
 }
 const f3=blocks.finance_f3
 if(f3!==null){
  const x=rec(f3,'finance_f3'),anchor=i(x.anchor_year,'finance_f3.anchor_year'),start=i(x.window_start_year,'finance_f3.window_start_year'),points=ar(x.points,'finance_f3.points'),summaries=[rec(x.revenue_summary,'finance_f3.revenue_summary'),rec(x.assets_summary,'finance_f3.assets_summary')] as const
  if(start!==anchor-6n||!same(points.map((q,n)=>i(rec(q,`finance_f3.points[${n}]`).year,'year')),Array.from({length:7},(_,n)=>start+BigInt(n)))||s(summaries[0].metric_id,'metric_id')!=='revenue_2110'||s(summaries[1].metric_id,'metric_id')!=='assets_1600')fail('F3 shape mismatch')
  for(const [seriesIndex,summary] of summaries.entries()){
    const moneyKey=seriesIndex===0?'revenue_2110':'assets_1600',yoyKey=seriesIndex===0?'revenue_yoy_decimal':'assets_yoy_decimal',available:{year:bigint;value:Dec}[]=[],values:(Dec|null)[]=[]
    points.forEach((q,n)=>{const point=rec(q,`finance_f3.points[${n}]`),moneyValue=point[moneyKey],geometry=ar(point.geometry_by_metric,`finance_f3.points[${n}].geometry_by_metric`)[seriesIndex],value=moneyValue===null?null:moneySource(moneyValue,`finance_f3.points[${n}].${moneyKey}`);values.push(value);if((value===null)!==(geometry===null))fail('F3 gap geometry mismatch');if(value!==null){const geometryValue=d(rec(geometry,'geometry').ratio_decimal,'ratio');if(cmp(geometryValue,value)!==0)fail('F3 geometry mismatch');available.push({year:i(point.year,'year'),value})}exactNullableDecimal(point[yoyKey],expectedYoy(n===0?null:values[n-1],value),`finance_f3.points[${n}].${yoyKey}`)})
    if(available.length===0){if([summary.comparison_start_year,summary.comparison_end_year,summary.multiple_decimal,summary.change,summary.axis].some(value=>value!==null))fail('F3 empty summary mismatch');continue}
    exactAxis(summary.axis,available.map(item=>item.value),`finance_f3.${moneyKey}.axis`);for(const item of available)inAxis(item.value,summary.axis,`finance_f3.${moneyKey}.axis`)
    if(available.length===1){if([summary.comparison_start_year,summary.comparison_end_year,summary.multiple_decimal,summary.change].some(value=>value!==null))fail('F3 single-point summary mismatch');continue}
    const first=available[0],last=available[available.length-1],expectedMultiple=cmp(first.value,zero())>0&&cmp(last.value,zero())>0?quantizedRatio(last.value,first.value):null
    if(i(summary.comparison_start_year,'comparison_start_year')!==first.year||i(summary.comparison_end_year,'comparison_end_year')!==last.year)fail('F3 comparison years mismatch')
    exactNullableDecimal(summary.multiple_decimal,expectedMultiple,'F3 multiple')
    if(summary.change===null||cmp(moneySource(summary.change,'F3 change'),sub(last.value,first.value))!==0)fail('F3 change mismatch')
  }
 }
 const f4=blocks.finance_f4
 if(f4!==null){
  const x=rec(f4,'finance_f4'),sources=[moneySource(x.revenue_2110,'f4.revenue'),moneySource(x.gross_2100,'f4.gross'),moneySource(x.operating_2200,'f4.operating'),moneySource(x.net_2400,'f4.net')] as const,rawRatios=[x.revenue_per_100_decimal,x.gross_per_100_decimal,x.operating_per_100_decimal,x.net_per_100_decimal] as const,geometries=ar(x.geometry_by_metric,'finance_f4.geometry_by_metric'),mode=s(x.mode,'finance_f4.mode'),positiveRevenue=cmp(sources[0],zero())>0
  if(!positiveRevenue){if(mode!=='denominator_unavailable'||x.axis!==null||rawRatios.some(value=>value!==null)||geometries.some(value=>value!==null))fail('F4 unavailable denominator shape mismatch')}
  else{
    if(mode!=='per_100'||x.axis===null||rawRatios.some(value=>value===null)||geometries.some(value=>value===null))fail('F4 available denominator shape mismatch')
    const ratios=[{coefficient:100n,scale:0n},quantizedRatio(sources[1],sources[0],100n),quantizedRatio(sources[2],sources[0],100n),quantizedRatio(sources[3],sources[0],100n)] as const
    rawRatios.forEach((value,index)=>exactNullableDecimal(value,ratios[index],`F4[${index}]`));exactAxis(x.axis,ratios,'F4 axis')
    geometries.forEach((geometry,index)=>{exactInterval(geometry,zero(),ratios[index],`F4[${index}].geometry`);intervalInAxis(geometry,x.axis,`F4[${index}].geometry`)})
  }
 }
 const f5=blocks.finance_f5
 if(f5!==null){
  const x=rec(f5,'finance_f5'),anchor=i(x.anchor_year,'finance_f5.anchor_year'),years=ar(x.years,'finance_f5.years').map((q,n)=>i(q,`finance_f5.years[${n}]`)),expected=Array.from({length:7},(_,n)=>anchor-6n+BigInt(n)),rows=ar(x.rows,'finance_f5.rows')
  if(!same(years,expected)||!same(rows.map((q,n)=>s(rec(q,`finance_f5.rows[${n}]`).metric_id,'metric_id')),F5_IDS)||!same(rows.map((q,n)=>s(rec(q,`finance_f5.rows[${n}]`).label,'label')),F5_LABELS))fail('F5 shape mismatch')
  rows.forEach((q,n)=>{const cells=ar(rec(q,`finance_f5.rows[${n}]`).cells,'cells'),values=cells.map((cell,index)=>{const value=rec(cell,`F5[${n}].cells[${index}]`).value;return value===null?null:moneySource(value,`F5[${n}].cells[${index}].value`)});if(!same(cells.map((z,j)=>i(rec(z,`cell[${j}]`).year,'year')),years))fail('F5 cell years mismatch');cells.forEach((cell,index)=>exactNullableDecimal(rec(cell,`F5[${n}].cells[${index}]`).yoy_decimal,expectedYoy(index===0?null:values[index-1],values[index]),`F5[${n}].cells[${index}].yoy_decimal`))})
 }
}

export function validateCompanyPublicH2Semantics(root:Obj):void {
 nfc(root); monies(root); axes(root); detailScopes(root); finance(root)
 const identity=rec(root.identity,'identity'), req=rec(rec(root.blocks,'blocks').requisites,'blocks.requisites')
 const owners=ar(req.owners,'owners');owners.forEach((q,n)=>{const x=rec(q,`owners[${n}]`);if((x.share_percent_decimal===null)!==(x.share_display===null))fail('owner share fields must co-occur')})
 if(ar(req.additional_activities,'additional_activities').some((q,n)=>rec(q,`additional_activities[${n}]`).is_primary===true))fail('invalid requisites ordering')
 const modes=ar(req.tax_modes,'tax_modes').map((q,n)=>s(rec(q,`tax_modes[${n}]`).mode_id,'mode_id'));if(!same(modes,[...modes].sort()))fail('invalid requisites ordering')
 const narrative=rec(root.narrative,'narrative'),statement=ar(narrative.statement_ids,'statement_ids').map((q,n)=>s(q,`statement_ids[${n}]`));if(!unique(statement))fail('invalid narrative')
 ar(narrative.comments,'comments').forEach((q,n)=>{const ids=ar(rec(q,`comments[${n}]`).evidence_ids,'evidence_ids').map((z,j)=>s(z,`evidence_ids[${j}]`));if(!unique(ids))fail('invalid chart comment')})
 if(!same(ar(root.block_order,'block_order').map((q,n)=>s(q,`block_order[${n}]`)),BLOCK_ORDER))fail('invalid block order')
 const coverage=ar(root.coverage,'coverage');if(!same(coverage.map((q,n)=>s(rec(q,`coverage[${n}]`).block_id,'block_id')),COVERAGE))fail('invalid coverage order')
 coverage.forEach((q,n)=>{const x=rec(q,`coverage[${n}]`),codes=ar(x.limitation_codes,'limitation_codes').map((z,j)=>s(z,`code[${j}]`)),state=s(x.state,'state');if(!unique(codes)||(!['available','available_empty','missing'].includes(state)&&codes.length===0))fail('invalid coverage')})
 const limitations=ar(root.limitations,'limitations'),known=limitations.map((q,n)=>s(rec(q,`limitations[${n}]`).code,'code'));if(!unique(known))fail('invalid limitation');limitations.forEach((q,n)=>{const x=rec(q,`limitations[${n}]`);if(x.block_id!==null&&!BLOCK_IDS.includes(s(x.block_id,'limitation.block_id') as typeof BLOCK_IDS[number]))fail('invalid limitation')});coverage.forEach((q,n)=>ar(rec(q,`coverage[${n}]`).limitation_codes,'limitation_codes').forEach((z,j)=>{if(!known.includes(s(z,`coverage[${n}].limitation_codes[${j}]`)))fail('coverage references missing limitation')}))
 const sources=ar(root.sources,'sources').map((q,n)=>s(rec(q,`sources[${n}]`).dataset,'dataset'));if(sources.length<1||sources.length>3||!same(sources,['counterparty','finance','arbitration'].slice(0,sources.length)))fail('invalid source order')
 const version=s(root.report_version,'report_version'),cap=s(root.snapshot_capability,'snapshot_capability'),scopeValue=s(root.projection_scope,'projection_scope');if((version==='3')!==(cap==='card_v2')||((version==='1'||version==='2')&&root.indexable===true)||(root.indexable===true&&scopeValue!=='active_publication'))fail('invalid version/indexability')
 const canonical=s(root.canonical_path,'canonical_path'),inn=s(identity.inn,'identity.inn'),legacy=new RegExp(`^/company/${inn}-[a-z0-9]+(?:-[a-z0-9]+)*$`).test(canonical),v2=new RegExp(`^/company/(?:ooo|ao|oao|zao|pao|ip)-[a-z0-9]+(?:-[a-z0-9]+)*-${inn}$`).test(canonical);if(!legacy&&!v2)fail('canonical path does not bind INN')
 const actions=ar(root.actions,'actions'),crumbs=ar(root.breadcrumbs,'breadcrumbs');if(s(rec(actions[0],'actions[0]').action_id,'action_id')!=='check_another_company'||s(rec(actions[0],'actions[0]').label,'label')!=='Проверить другую компанию'||s(rec(actions[0],'actions[0]').path,'path')!=='/'||s(rec(actions[1],'actions[1]').action_id,'action_id')!=='prepare_claim'||s(rec(actions[1],'actions[1]').label,'label')!=='Подготовить претензию'||s(rec(crumbs[0],'breadcrumbs[0]').label,'label')!=='Главная'||s(rec(crumbs[0],'breadcrumbs[0]').path,'path')!=='/'||rec(crumbs[0],'breadcrumbs[0]').current!==false||rec(crumbs[1],'breadcrumbs[1]').current!==true||s(rec(crumbs[1],'breadcrumbs[1]').label,'label')!==s(identity.display_name,'identity.display_name')||s(rec(crumbs[1],'breadcrumbs[1]').path,'path')!==canonical)fail('invalid navigation')
 const claim=`/claims?report_id=${s(root.report_id,'report_id')}`;if(s(rec(actions[1],'actions[1]').path,'path')!==claim||s(rec(root.primary_claim_cta,'primary_claim_cta').path,'primary_claim_cta.path')!==claim)fail('invalid Claims cross-binding')
 const blocks=rec(root.blocks,'blocks');for(const id of COVERAGE.slice(2,-1)){const blockKey=id as keyof typeof blocks,coverageItem=rec(coverage.find(q=>s(rec(q,'coverage').block_id,'block_id')===id),'coverage'),state=s(coverageItem.state,'coverage.state'),hasBlock=blocks[blockKey]!==null;if(hasBlock!==['available','available_empty','partial'].includes(state))fail('coverage and block disagree')}
 validateArbitrationPolicyV3(root as CompanyPublicH2)
}
