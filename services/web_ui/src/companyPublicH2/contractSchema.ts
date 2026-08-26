import { CompanyPublicH2ContractError } from './contractErrors'
import { isStrictJsonInteger, isStrictJsonObject, type StrictJsonInteger, type StrictJsonObject, type StrictJsonValue } from './strictJson'

/** Closed wire-schema validation. Cross-record rules are in contractSemantics. */
export type Obj = StrictJsonObject
export interface PublicH2StatusDto extends StrictJsonObject {
  readonly state: 'active' | 'inactive' | 'other'
  readonly code: string
  readonly label: string
  readonly effective_date: string | null
}
export interface PublicH2IdentityDto extends StrictJsonObject {
  readonly display_name: string
  readonly legal_full_name: string
  readonly short_name: string | null
  readonly inn: string
  readonly ogrn: string | null
  readonly kpp: string | null
  readonly registration_date: string | null
  readonly dissolution_date: string | null
  readonly status: PublicH2StatusDto | null
}
export interface PublicH2LabeledCodeDto extends StrictJsonObject { readonly code: string; readonly label: string }
export interface PublicH2AddressDto extends StrictJsonObject { readonly display: string; readonly region: string | null; readonly is_inaccuracy: boolean | null }
export interface PublicH2CharterCapitalDto extends StrictJsonObject { readonly source_decimal: string; readonly unit_id: string; readonly display_exact: string; readonly unit_policy_version: string }
export interface PublicH2TaxModeDto extends StrictJsonObject { readonly mode_id: string; readonly label: string; readonly applies: true; readonly effective_date: string | null }
export interface PublicH2ActivityDto extends StrictJsonObject { readonly code: string; readonly label: string; readonly is_primary: boolean }
export interface PublicH2ManagerDto extends StrictJsonObject { readonly name: string; readonly role: string; readonly appointed_at: string | null; readonly is_inaccuracy: boolean | null }
export interface PublicH2OwnerDto extends StrictJsonObject { readonly display_name: string; readonly owner_type: 'person' | 'organization' | 'state'; readonly share_percent_decimal: string | null; readonly share_display: string | null; readonly effective_date: string | null }
export interface PublicH2EmployeesDto extends StrictJsonObject { readonly count: StrictJsonInteger; readonly period: string; readonly effective_date: string | null }
export interface PublicH2RequisitesDto extends StrictJsonObject {
  readonly legal_form: PublicH2LabeledCodeDto | null
  readonly address: PublicH2AddressDto | null
  readonly charter_capital: PublicH2CharterCapitalDto | null
  readonly tax_modes: readonly PublicH2TaxModeDto[]
  readonly primary_activity: PublicH2ActivityDto | null
  readonly additional_activities: readonly PublicH2ActivityDto[]
  readonly managers: readonly PublicH2ManagerDto[]
  readonly owners: readonly PublicH2OwnerDto[]
  readonly employees: PublicH2EmployeesDto | null
  readonly tax_authority: PublicH2LabeledCodeDto | null
}
export interface PublicH2NarrativeDto extends StrictJsonObject {
  readonly mode: 'artifact' | 'deterministic_fallback'
  readonly renderer_version: string
  readonly description: string
  readonly statement_ids: readonly string[]
  readonly comments: readonly StrictJsonObject[]
  readonly render_digest: string
}
export interface PublicH2ViewDto extends StrictJsonObject { readonly view_id: string }
export interface PublicH2MoneyDto extends StrictJsonObject {
  readonly source_thousand_decimal: string
  readonly rub_decimal: string
  readonly million_decimal: string
  readonly display_exact: string
  readonly display_compact: string
  readonly unit_id: 'RUB'
  readonly unit_policy_version: 'datanewton_finance_thousand_rub_v2'
}
export interface PublicH2AxisDto extends StrictJsonObject { readonly axis_min_decimal: string; readonly axis_max_decimal: string }
export interface PublicH2IntervalDto extends StrictJsonObject { readonly start_ratio_decimal: string; readonly end_ratio_decimal: string }
export interface PublicH2PointDto extends StrictJsonObject { readonly ratio_decimal: string }
export interface PublicH2FinanceF1Dto extends PublicH2ViewDto {
  readonly view_id: 'finance_f1_liquidity'; readonly year: StrictJsonInteger
  readonly cash_1250: PublicH2MoneyDto; readonly investments_1240: PublicH2MoneyDto; readonly receivables_1230: PublicH2MoneyDto; readonly short_liabilities_1500: PublicH2MoneyDto
  readonly available_without_inventory: PublicH2MoneyDto; readonly difference: PublicH2MoneyDto; readonly axis: PublicH2AxisDto
  readonly segments: readonly { readonly metric_id: '1250' | '1240' | '1230' | '1500'; readonly value: PublicH2MoneyDto; readonly geometry: PublicH2IntervalDto }[]
}
export interface PublicH2FinanceF2PeriodDto extends StrictJsonObject {
  readonly year: StrictJsonInteger; readonly state: 'available' | 'gap' | 'denominator_unavailable'; readonly equity_1300: PublicH2MoneyDto | null; readonly long_liabilities_1400: PublicH2MoneyDto | null; readonly short_liabilities_1500: PublicH2MoneyDto | null; readonly debt: PublicH2MoneyDto | null; readonly denominator: PublicH2MoneyDto | null
  readonly equity_share_decimal: string | null; readonly debt_share_decimal: string | null; readonly mode: 'stacked_100' | 'diverging_signed' | 'unavailable'; readonly axis: PublicH2AxisDto | null; readonly geometry_by_metric: readonly [PublicH2IntervalDto | null, PublicH2IntervalDto | null]
}
export interface PublicH2FinanceF2Dto extends PublicH2ViewDto { readonly view_id: 'finance_f2_funding'; readonly anchor_year: StrictJsonInteger; readonly window_start_year: StrictJsonInteger; readonly periods: readonly PublicH2FinanceF2PeriodDto[] }
export interface PublicH2FinanceF3PointDto extends StrictJsonObject { readonly year: StrictJsonInteger; readonly revenue_2110: PublicH2MoneyDto | null; readonly assets_1600: PublicH2MoneyDto | null; readonly revenue_yoy_decimal: string | null; readonly assets_yoy_decimal: string | null; readonly geometry_by_metric: readonly [PublicH2PointDto | null, PublicH2PointDto | null] }
export interface PublicH2FinanceF3SummaryDto extends StrictJsonObject { readonly metric_id: 'revenue_2110' | 'assets_1600'; readonly comparison_start_year: StrictJsonInteger | null; readonly comparison_end_year: StrictJsonInteger | null; readonly multiple_decimal: string | null; readonly change: PublicH2MoneyDto | null; readonly axis: PublicH2AxisDto | null }
export interface PublicH2FinanceF3Dto extends PublicH2ViewDto { readonly view_id: 'finance_f3_growth'; readonly anchor_year: StrictJsonInteger; readonly window_start_year: StrictJsonInteger; readonly points: readonly PublicH2FinanceF3PointDto[]; readonly revenue_summary: PublicH2FinanceF3SummaryDto; readonly assets_summary: PublicH2FinanceF3SummaryDto }
export interface PublicH2FinanceF4Dto extends PublicH2ViewDto { readonly view_id: 'finance_f4_profit_per_100'; readonly year: StrictJsonInteger; readonly revenue_2110: PublicH2MoneyDto; readonly gross_2100: PublicH2MoneyDto; readonly operating_2200: PublicH2MoneyDto; readonly net_2400: PublicH2MoneyDto; readonly revenue_per_100_decimal: '100' | null; readonly gross_per_100_decimal: string | null; readonly operating_per_100_decimal: string | null; readonly net_per_100_decimal: string | null; readonly mode: 'per_100' | 'denominator_unavailable'; readonly axis: PublicH2AxisDto | null; readonly geometry_by_metric: readonly [PublicH2IntervalDto | null, PublicH2IntervalDto | null, PublicH2IntervalDto | null, PublicH2IntervalDto | null] }
export interface PublicH2FinanceF5CellDto extends StrictJsonObject { readonly year: StrictJsonInteger; readonly value: PublicH2MoneyDto | null; readonly yoy_decimal: string | null }
export interface PublicH2FinanceF5Dto extends PublicH2ViewDto { readonly view_id: 'finance_f5_yearly_table'; readonly anchor_year: StrictJsonInteger; readonly years: readonly StrictJsonInteger[]; readonly rows: readonly { readonly metric_id: '2110' | '1600' | '1250' | '1240' | '1230' | '1210' | '1500' | '1300' | '2400'; readonly label: string; readonly cells: readonly PublicH2FinanceF5CellDto[] }[] }
export interface PublicH2BlocksDto extends StrictJsonObject {
  readonly requisites: PublicH2RequisitesDto
  readonly finance_f1: PublicH2FinanceF1Dto | null
  readonly finance_f2: PublicH2FinanceF2Dto | null
  readonly finance_f3: PublicH2FinanceF3Dto | null
  readonly finance_f4: PublicH2FinanceF4Dto | null
  readonly finance_f5: PublicH2FinanceF5Dto | null
  readonly arbitration_a1: PublicH2ViewDto | null
  readonly arbitration_a2: PublicH2ViewDto | null
  readonly arbitration_a3: PublicH2ViewDto | null
  readonly arbitration_a4: PublicH2ViewDto | null
  readonly arbitration_a5: PublicH2ViewDto | null
}
export interface PublicH2CoverageItemDto extends StrictJsonObject {
  readonly block_id: string
  readonly state: string
  readonly population_scope: string
  readonly total: StrictJsonInteger | null
  readonly returned: StrictJsonInteger | null
  readonly eligible: StrictJsonInteger | null
  readonly limitation_codes: readonly string[]
}
export interface PublicH2SourceItemDto extends StrictJsonObject { readonly dataset: string; readonly received_at: string; readonly effective_at: string | null; readonly period: string | null; readonly normalization_version: string; readonly evidence_version: string }
export interface PublicH2LimitationDto extends StrictJsonObject { readonly code: string; readonly block_id: string | null; readonly field_id: string | null; readonly message: string }
export interface PublicH2ActionDto extends StrictJsonObject { readonly action_id: 'check_another_company' | 'prepare_claim'; readonly label: string; readonly path: string }
export interface PublicH2BreadcrumbDto extends StrictJsonObject { readonly label: string; readonly path: string; readonly current: boolean }
export interface PublicH2ClaimCtaDto extends StrictJsonObject { readonly action_id: 'prepare_claim'; readonly heading: 'Вам задолжали?'; readonly desktop_copy: 'Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!'; readonly button_label: 'Создать претензию'; readonly path: string }

/** Fully validated immutable browser-facing DTO. Integer leaves stay exact tokens. */
export interface CompanyPublicH2 extends StrictJsonObject {
  readonly contract_version: 'company_public_h2_v1'
  readonly projection_digest: string
  readonly report_id: string
  readonly report_version: '1' | '2' | '3'
  readonly chart_facts_version: 'company_card_chart_facts_v1'
  readonly chart_facts_hash: string
  readonly snapshot_capability: 'legacy_read_only' | 'card_v2'
  readonly projection_scope: 'active_publication' | 'staged_publication' | 'latest_unpublished'
  readonly canonical_path: string
  readonly indexable: boolean
  readonly checked_at: string
  readonly checked_date: string
  readonly checked_date_display: string
  readonly identity: PublicH2IdentityDto
  readonly narrative: PublicH2NarrativeDto
  readonly block_order: readonly string[]
  readonly blocks: PublicH2BlocksDto
  readonly coverage: readonly PublicH2CoverageItemDto[]
  readonly sources: readonly PublicH2SourceItemDto[]
  readonly limitations: readonly PublicH2LimitationDto[]
  readonly actions: readonly [PublicH2ActionDto, PublicH2ActionDto]
  readonly breadcrumbs: readonly [PublicH2BreadcrumbDto, PublicH2BreadcrumbDto]
  readonly primary_claim_cta: PublicH2ClaimCtaDto
}
export const BLOCK_IDS = ['requisites', 'narrative', 'finance_f1', 'finance_f2', 'finance_f3', 'finance_f4', 'finance_f5', 'arbitration_a1', 'arbitration_a2', 'arbitration_a3', 'arbitration_a4', 'arbitration_a5', 'sources_limitations'] as const
export const VIEW_IDS = ['finance_f1_liquidity','finance_f2_funding','finance_f3_growth','finance_f4_profit_per_100','finance_f5_yearly_table','arbitration_a1_activity','arbitration_a2_roles','arbitration_a3_outcomes','arbitration_a4_case_amounts','arbitration_a5_opponents'] as const
const CODE=/^[A-Za-z0-9_.-]{1,64}$/, DECIMAL=/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$/, DATE=/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/, UTC=/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$/, ACTIVITY=/^[0-9.]{2,16}$/, UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, PATH=/^\/[A-Za-z0-9_./?=&-]{1,2047}$/
const fail=(m:string):never=>{throw new CompanyPublicH2ContractError(m)}
export const object=(v:StrictJsonValue|undefined,p:string):Obj=>isStrictJsonObject(v)?v:fail(p+' must be object')
export const keys=(v:Obj,e:readonly string[],p:string)=>{const a=Object.keys(v);if(a.length!==e.length||a.some(k=>!e.includes(k)))fail(`${p} has unexpected or missing fields`)}
export const required=(v:Obj,k:string,p:string):StrictJsonValue=>{if(!Object.hasOwn(v,k))fail(`${p}.${k} missing`);return v[k]}
export const string=(v:StrictJsonValue|undefined,p:string):string=>typeof v==='string'?v:fail(p+' must be string')
const pythonWhitespace=(code:number):boolean=>(code>=0x09&&code<=0x0d)||(code>=0x1c&&code<=0x20)||code===0x85||code===0xa0||code===0x1680||(code>=0x2000&&code<=0x200a)||code===0x2028||code===0x2029||code===0x202f||code===0x205f||code===0x3000
const pythonStrip=(value:string):string=>{const scalars=[...value];let start=0,end=scalars.length;while(start<end&&pythonWhitespace(scalars[start].codePointAt(0)!))start+=1;while(end>start&&pythonWhitespace(scalars[end-1].codePointAt(0)!))end-=1;return scalars.slice(start,end).join('')}
export const text=(v:StrictJsonValue|undefined,p:string,m=2048):string=>{const x=string(v,p);if(!pythonStrip(x)||[...x].length>m)fail(`${p} must be nonblank and bounded`);return x}
export const integer=(v:StrictJsonValue|undefined,p:string,min?:bigint,max?:bigint):StrictJsonInteger=>{const item=isStrictJsonInteger(v)?v:fail(p+' must be integer');if((min!==undefined&&item.value<min)||(max!==undefined&&item.value>max))fail(p+' is out of range');return item}
const arr=(v:StrictJsonValue|undefined,p:string,min=0,max=Number.MAX_SAFE_INTEGER):readonly StrictJsonValue[]=>{const item=Array.isArray(v)?v:fail(p+' invalid array');if(item.length<min||item.length>max)fail(p+' invalid array cardinality');return item}
const nullable=(v:StrictJsonValue|undefined,p:string,f:(v:StrictJsonValue,p:string)=>void)=>{const item=v===undefined?fail(p+' missing'):v;if(item!==null)f(item,p)}
const lit=(v:StrictJsonValue|undefined,e:readonly (string|boolean)[],p:string)=>{if(!e.includes(v as string|boolean))fail(`${p} has invalid literal`)}
const code=(v:StrictJsonValue|undefined,p:string)=>{const x=string(v,p);if(!CODE.test(x))fail(`${p} invalid code`);return x}
const dec=(v:StrictJsonValue|undefined,p:string)=>{const x=string(v,p);if(!DECIMAL.test(x))fail(`${p} invalid decimal`);return x}
const date=(v:StrictJsonValue|undefined,p:string)=>{if(!DATE.test(string(v,p)))fail(`${p} invalid date`)}
const optTruthyDate=(v:StrictJsonValue|undefined,p:string)=>nullable(v,p,(item,path)=>{const value=string(item,path);if(value)date(item,path)})
const bool=(v:StrictJsonValue,p:string)=>{if(typeof v!=='boolean')fail(`${p} must be boolean`)}
const tuple=(v:StrictJsonValue|undefined,p:string,n:number,f:(v:StrictJsonValue,p:string)=>void)=>arr(v,p,n,n).forEach((x,i)=>f(x,`${p}[${i}]`))
const optionalText=(v:StrictJsonValue|undefined,p:string)=>nullable(v,p,text)
const optionalTruthyText=(v:StrictJsonValue|undefined,p:string)=>nullable(v,p,(item,path)=>{const value=string(item,path);if(value)text(item,path)})
const optionalString=(v:StrictJsonValue|undefined,p:string)=>nullable(v,p,string)

const labeled=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['code','label'],p);code(x.code,`${p}.code`);text(x.label,`${p}.label`)}
const address=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['display','region','is_inaccuracy'],p);text(x.display,`${p}.display`);optionalTruthyText(x.region,`${p}.region`);nullable(x.is_inaccuracy,`${p}.is_inaccuracy`,bool)}
const charter=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['source_decimal','unit_id','display_exact','unit_policy_version'],p);dec(x.source_decimal,`${p}.source_decimal`);code(x.unit_id,`${p}.unit_id`);text(x.display_exact,`${p}.display_exact`);code(x.unit_policy_version,`${p}.unit_policy_version`)}
const activity=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['code','label','is_primary'],p);if(!ACTIVITY.test(string(x.code,`${p}.code`)))fail(`${p}.code invalid activity`);text(x.label,`${p}.label`);bool(x.is_primary,`${p}.is_primary`)}
const taxMode=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['mode_id','label','applies','effective_date'],p);lit(x.mode_id,['common_mode','usn_sign','ausn_sign','envd_sign','eshn_sign','npd_sign','psn_sign','srp_sign'],`${p}.mode_id`);string(x.label,`${p}.label`);lit(x.applies,[true],`${p}.applies`);optionalString(x.effective_date,`${p}.effective_date`)}
const manager=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['name','role','appointed_at','is_inaccuracy'],p);string(x.name,`${p}.name`);string(x.role,`${p}.role`);optionalString(x.appointed_at,`${p}.appointed_at`);nullable(x.is_inaccuracy,`${p}.is_inaccuracy`,bool)}
const owner=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['display_name','owner_type','share_percent_decimal','share_display','effective_date'],p);text(x.display_name,`${p}.display_name`);lit(x.owner_type,['person','organization','state'],`${p}.owner_type`);nullable(x.share_percent_decimal,`${p}.share_percent_decimal`,dec);optionalString(x.share_display,`${p}.share_display`);optionalString(x.effective_date,`${p}.effective_date`)}
const employees=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['count','period','effective_date'],p);integer(x.count,`${p}.count`,0n,999999999n);string(x.period,`${p}.period`);optionalString(x.effective_date,`${p}.effective_date`)}
const requisites=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['legal_form','address','charter_capital','tax_modes','primary_activity','additional_activities','managers','owners','employees','tax_authority'],p);nullable(x.legal_form,`${p}.legal_form`,labeled);nullable(x.address,`${p}.address`,address);nullable(x.charter_capital,`${p}.charter_capital`,charter);arr(x.tax_modes,`${p}.tax_modes`,0,8).forEach((q,i)=>taxMode(q,`${p}.tax_modes[${i}]`));nullable(x.primary_activity,`${p}.primary_activity`,activity);arr(x.additional_activities,`${p}.additional_activities`,0,20).forEach((q,i)=>activity(q,`${p}.additional_activities[${i}]`));arr(x.managers,`${p}.managers`,0,20).forEach((q,i)=>manager(q,`${p}.managers[${i}]`));arr(x.owners,`${p}.owners`,0,50).forEach((q,i)=>owner(q,`${p}.owners[${i}]`));nullable(x.employees,`${p}.employees`,employees);nullable(x.tax_authority,`${p}.tax_authority`,labeled)}
const money=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['source_thousand_decimal','rub_decimal','million_decimal','display_exact','display_compact','unit_id','unit_policy_version'],p);for(const k of ['source_thousand_decimal','rub_decimal','million_decimal'] as const)dec(x[k],`${p}.${k}`);text(x.display_exact,`${p}.display_exact`);text(x.display_compact,`${p}.display_compact`);lit(x.unit_id,['RUB'],`${p}.unit_id`);lit(x.unit_policy_version,['datanewton_finance_thousand_rub_v2'],`${p}.unit_policy_version`)}
const axis=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['axis_min_decimal','axis_max_decimal'],p);dec(x.axis_min_decimal,`${p}.axis_min_decimal`);dec(x.axis_max_decimal,`${p}.axis_max_decimal`)}
const interval=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['start_ratio_decimal','end_ratio_decimal'],p);dec(x.start_ratio_decimal,`${p}.start_ratio_decimal`);dec(x.end_ratio_decimal,`${p}.end_ratio_decimal`)}
const point=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['ratio_decimal'],p);dec(x.ratio_decimal,`${p}.ratio_decimal`)}
const scope=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['population_scope','source_total','rows_received','eligible_total','shown','cap','label'],p);lit(x.population_scope,['complete_collection','returned_slice'],`${p}.population_scope`);nullable(x.source_total,`${p}.source_total`,(q,z)=>integer(q,z,0n));integer(x.rows_received,`${p}.rows_received`,0n);integer(x.eligible_total,`${p}.eligible_total`,0n);integer(x.shown,`${p}.shown`,0n,20n);integer(x.cap,`${p}.cap`,20n,20n);text(x.label,`${p}.label`)}

const f1=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','year','cash_1250','investments_1240','receivables_1230','short_liabilities_1500','available_without_inventory','difference','axis','segments'],p);lit(x.view_id,['finance_f1_liquidity'],`${p}.view_id`);integer(x.year,`${p}.year`,1900n,2100n);for(const k of ['cash_1250','investments_1240','receivables_1230','short_liabilities_1500','available_without_inventory','difference'] as const)money(x[k],`${p}.${k}`);axis(x.axis,`${p}.axis`);tuple(x.segments,`${p}.segments`,4,(q,z)=>{const y=object(q,z);keys(y,['metric_id','value','geometry'],z);lit(y.metric_id,['1250','1240','1230','1500'],`${z}.metric_id`);money(y.value,`${z}.value`);interval(y.geometry,`${z}.geometry`)})}
const f2Period=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['year','state','equity_1300','long_liabilities_1400','short_liabilities_1500','debt','denominator','equity_share_decimal','debt_share_decimal','mode','axis','geometry_by_metric'],p);integer(x.year,`${p}.year`,1900n,2100n);lit(x.state,['available','gap','denominator_unavailable'],`${p}.state`);for(const k of ['equity_1300','long_liabilities_1400','short_liabilities_1500','debt','denominator'] as const)nullable(x[k],`${p}.${k}`,money);nullable(x.equity_share_decimal,`${p}.equity_share_decimal`,dec);nullable(x.debt_share_decimal,`${p}.debt_share_decimal`,dec);lit(x.mode,['stacked_100','diverging_signed','unavailable'],`${p}.mode`);nullable(x.axis,`${p}.axis`,axis);tuple(x.geometry_by_metric,`${p}.geometry_by_metric`,2,(q,z)=>nullable(q,z,interval))}
const f2=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','anchor_year','window_start_year','periods'],p);lit(x.view_id,['finance_f2_funding'],`${p}.view_id`);integer(x.anchor_year,`${p}.anchor_year`,1900n,2100n);integer(x.window_start_year,`${p}.window_start_year`);tuple(x.periods,`${p}.periods`,7,f2Period)}
const f3Point=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['year','revenue_2110','assets_1600','revenue_yoy_decimal','assets_yoy_decimal','geometry_by_metric'],p);integer(x.year,`${p}.year`,1900n,2100n);nullable(x.revenue_2110,`${p}.revenue_2110`,money);nullable(x.assets_1600,`${p}.assets_1600`,money);nullable(x.revenue_yoy_decimal,`${p}.revenue_yoy_decimal`,dec);nullable(x.assets_yoy_decimal,`${p}.assets_yoy_decimal`,dec);tuple(x.geometry_by_metric,`${p}.geometry_by_metric`,2,(q,z)=>nullable(q,z,point))}
const f3Summary=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['metric_id','comparison_start_year','comparison_end_year','multiple_decimal','change','axis'],p);lit(x.metric_id,['revenue_2110','assets_1600'],`${p}.metric_id`);for(const k of ['comparison_start_year','comparison_end_year'] as const)nullable(x[k],`${p}.${k}`,(q,z)=>integer(q,z,1900n,2100n));nullable(x.multiple_decimal,`${p}.multiple_decimal`,dec);nullable(x.change,`${p}.change`,money);nullable(x.axis,`${p}.axis`,axis)}
const f3=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','anchor_year','window_start_year','points','revenue_summary','assets_summary'],p);lit(x.view_id,['finance_f3_growth'],`${p}.view_id`);integer(x.anchor_year,`${p}.anchor_year`,1900n,2100n);integer(x.window_start_year,`${p}.window_start_year`);tuple(x.points,`${p}.points`,7,f3Point);f3Summary(x.revenue_summary,`${p}.revenue_summary`);f3Summary(x.assets_summary,`${p}.assets_summary`)}
const f4=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','year','revenue_2110','gross_2100','operating_2200','net_2400','revenue_per_100_decimal','gross_per_100_decimal','operating_per_100_decimal','net_per_100_decimal','mode','axis','geometry_by_metric'],p);lit(x.view_id,['finance_f4_profit_per_100'],`${p}.view_id`);integer(x.year,`${p}.year`,1900n,2100n);for(const k of ['revenue_2110','gross_2100','operating_2200','net_2400'] as const)money(x[k],`${p}.${k}`);nullable(x.revenue_per_100_decimal,`${p}.revenue_per_100_decimal`,(q,z)=>lit(q,['100'],z));for(const k of ['gross_per_100_decimal','operating_per_100_decimal','net_per_100_decimal'] as const)nullable(x[k],`${p}.${k}`,dec);lit(x.mode,['per_100','denominator_unavailable'],`${p}.mode`);nullable(x.axis,`${p}.axis`,axis);tuple(x.geometry_by_metric,`${p}.geometry_by_metric`,4,(q,z)=>nullable(q,z,interval))}
const f5=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','anchor_year','years','rows'],p);lit(x.view_id,['finance_f5_yearly_table'],`${p}.view_id`);integer(x.anchor_year,`${p}.anchor_year`,1900n,2100n);tuple(x.years,`${p}.years`,7,(q,z)=>integer(q,z));tuple(x.rows,`${p}.rows`,9,(q,z)=>{const y=object(q,z);keys(y,['metric_id','label','cells'],z);lit(y.metric_id,['2110','1600','1250','1240','1230','1210','1500','1300','2400'],`${z}.metric_id`);string(y.label,`${z}.label`);tuple(y.cells,`${z}.cells`,7,(a,b)=>{const c=object(a,b);keys(c,['year','value','yoy_decimal'],b);integer(c.year,`${b}.year`,1900n,2100n);nullable(c.value,`${b}.value`,money);nullable(c.yoy_decimal,`${b}.yoy_decimal`,dec)})})}

const summary=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['source_total','rows_observed','unique_case_count','malformed_count','duplicate_identical_count','duplicate_conflict_count','collection_complete','completion_reason','calendar_complete','calendar_scope','calendar_start_year','calendar_end_year','calendar_evidence_version','observed_start_year','observed_end_year','unknown_year_count','zero_years_proven'],p);nullable(x.source_total,`${p}.source_total`,(q,z)=>integer(q,z,0n));for(const k of ['rows_observed','unique_case_count','malformed_count','duplicate_identical_count','duplicate_conflict_count','unknown_year_count'] as const)integer(x[k],`${p}.${k}`,0n);bool(x.collection_complete,`${p}.collection_complete`);string(x.completion_reason,`${p}.completion_reason`);bool(x.calendar_complete,`${p}.calendar_complete`);lit(x.calendar_scope,['unverified','all_time','bounded_interval'],`${p}.calendar_scope`);for(const k of ['calendar_start_year','calendar_end_year','observed_start_year','observed_end_year'] as const)nullable(x[k],`${p}.${k}`,(q,z)=>integer(q,z,1900n,2100n));optionalString(x.calendar_evidence_version,`${p}.calendar_evidence_version`);bool(x.zero_years_proven,`${p}.zero_years_proven`)}
const opponent=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['opponent_public_id','display_name','display_kind'],p);string(x.opponent_public_id,`${p}.opponent_public_id`);string(x.display_name,`${p}.display_name`);lit(x.display_kind,['legal','state','masked_natural','masked_unknown'],`${p}.display_kind`)}
const amount=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['source_decimal','source_currency_id','display_exact'],p);dec(x.source_decimal,`${p}.source_decimal`);string(x.source_currency_id,`${p}.source_currency_id`);string(x.display_exact,`${p}.display_exact`)}
const safeCase=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['case_public_id','case_number','year','role','outcome','result_detail','amount','start_date','update_date','days_to_last_update','instance_count','courts','opponents','public_case_url'],p);string(x.case_public_id,`${p}.case_public_id`);optionalString(x.case_number,`${p}.case_number`);nullable(x.year,`${p}.year`,(q,z)=>integer(q,z,1900n,2100n));lit(x.role,['plaintiff','respondent','other','unattributed'],`${p}.role`);lit(x.outcome,['won','lost','returned','unknown'],`${p}.outcome`);optionalString(x.result_detail,`${p}.result_detail`);nullable(x.amount,`${p}.amount`,amount);optionalString(x.start_date,`${p}.start_date`);optionalString(x.update_date,`${p}.update_date`);nullable(x.days_to_last_update,`${p}.days_to_last_update`,(q,z)=>integer(q,z,0n));nullable(x.instance_count,`${p}.instance_count`,(q,z)=>integer(q,z,0n));arr(x.courts,`${p}.courts`,0,10).forEach((q,i)=>string(q,`${p}.courts[${i}]`));arr(x.opponents,`${p}.opponents`,0,20).forEach((q,i)=>opponent(q,`${p}.opponents[${i}]`));optionalString(x.public_case_url,`${p}.public_case_url`)}
const roleDetail=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['role','scope','cases'],p);lit(x.role,['plaintiff','respondent','other','unattributed'],`${p}.role`);scope(x.scope,`${p}.scope`);arr(x.cases,`${p}.cases`,0,20).forEach((q,i)=>safeCase(q,`${p}.cases[${i}]`))}
const a1=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','summary','displayed_start_year','displayed_end_year','buckets','all_time_case_count'],p);lit(x.view_id,['arbitration_a1_activity'],`${p}.view_id`);summary(x.summary,`${p}.summary`);nullable(x.displayed_start_year,`${p}.displayed_start_year`,(q,z)=>integer(q,z,1900n,2100n));nullable(x.displayed_end_year,`${p}.displayed_end_year`,(q,z)=>integer(q,z,1900n,2100n));arr(x.buckets,`${p}.buckets`,0,11).forEach((q,i)=>{const b=object(q,`${p}.buckets[${i}]`);keys(b,['year','plaintiff_count','respondent_count','other_count','unattributed_count','total_count','role_details'],`${p}.buckets[${i}]`);nullable(b.year,`${p}.buckets[${i}].year`,(a,z)=>integer(a,z,1900n,2100n));for(const k of ['plaintiff_count','respondent_count','other_count','unattributed_count','total_count'] as const)integer(b[k],`${p}.buckets[${i}].${k}`,0n);tuple(b.role_details,`${p}.buckets[${i}].role_details`,4,roleDetail)});integer(x.all_time_case_count,`${p}.all_time_case_count`,0n)}
const bar=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['category_id','count','percent_decimal','scope','cases'],p);lit(x.category_id,['plaintiff','respondent','other','unattributed','won','lost','returned','unknown'],`${p}.category_id`);integer(x.count,`${p}.count`,0n);nullable(x.percent_decimal,`${p}.percent_decimal`,dec);scope(x.scope,`${p}.scope`);arr(x.cases,`${p}.cases`,0,20).forEach((q,i)=>safeCase(q,`${p}.cases[${i}]`))}
const a23=(v:StrictJsonValue,p:string,id:string)=>{const x=object(v,p);keys(x,['view_id','summary','denominator','bars'],p);lit(x.view_id,[id],`${p}.view_id`);summary(x.summary,`${p}.summary`);integer(x.denominator,`${p}.denominator`,0n);tuple(x.bars,`${p}.bars`,4,bar)}
const a4=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','summary','currency_groups','missing_amount_count','missing_currency_count'],p);lit(x.view_id,['arbitration_a4_case_amounts'],`${p}.view_id`);summary(x.summary,`${p}.summary`);arr(x.currency_groups,`${p}.currency_groups`,0,16).forEach((q,i)=>{const g=object(q,`${p}.currency_groups[${i}]`);keys(g,['source_currency_id','display_currency','axis','case_geometries','scope','cases'],`${p}.currency_groups[${i}]`);string(g.source_currency_id,`${p}.currency_groups[${i}].source_currency_id`);string(g.display_currency,`${p}.currency_groups[${i}].display_currency`);axis(g.axis,`${p}.currency_groups[${i}].axis`);arr(g.case_geometries,`${p}.currency_groups[${i}].case_geometries`,0,20).forEach((a,j)=>{const z=object(a,`${p}.currency_groups[${i}].case_geometries[${j}]`);keys(z,['case_public_id','geometry'],`${p}.currency_groups[${i}].case_geometries[${j}]`);string(z.case_public_id,`${p}.currency_groups[${i}].case_geometries[${j}].case_public_id`);interval(z.geometry,`${p}.currency_groups[${i}].case_geometries[${j}].geometry`)});scope(g.scope,`${p}.currency_groups[${i}].scope`);arr(g.cases,`${p}.currency_groups[${i}].cases`,0,20).forEach((a,j)=>safeCase(a,`${p}.currency_groups[${i}].cases[${j}]`))});integer(x.missing_amount_count,`${p}.missing_amount_count`,0n);integer(x.missing_currency_count,`${p}.missing_currency_count`,0n)}
const a5=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['view_id','summary','scope','groups','cases_without_safe_opponent','multi_opponent_case_count'],p);lit(x.view_id,['arbitration_a5_opponents'],`${p}.view_id`);summary(x.summary,`${p}.summary`);scope(x.scope,`${p}.scope`);arr(x.groups,`${p}.groups`,0,20).forEach((q,i)=>{const g=object(q,`${p}.groups[${i}]`);keys(g,['opponent_public_id','display_name','display_kind','case_count','case_scope','cases'],`${p}.groups[${i}]`);string(g.opponent_public_id,`${p}.groups[${i}].opponent_public_id`);string(g.display_name,`${p}.groups[${i}].display_name`);lit(g.display_kind,['legal','state','masked_natural','masked_unknown'],`${p}.groups[${i}].display_kind`);integer(g.case_count,`${p}.groups[${i}].case_count`,1n);scope(g.case_scope,`${p}.groups[${i}].case_scope`);arr(g.cases,`${p}.groups[${i}].cases`,0,20).forEach((a,j)=>safeCase(a,`${p}.groups[${i}].cases[${j}]`))});integer(x.cases_without_safe_opponent,`${p}.cases_without_safe_opponent`,0n);integer(x.multi_opponent_case_count,`${p}.multi_opponent_case_count`,0n)}
const narrative=(v:StrictJsonValue,p:string)=>{const x=object(v,p);keys(x,['mode','renderer_version','description','statement_ids','comments','render_digest'],p);lit(x.mode,['artifact','deterministic_fallback'],`${p}.mode`);code(x.renderer_version,`${p}.renderer_version`);const d=string(x.description,`${p}.description`);if([...d].length<400||[...d].length>700)fail(`${p}.description invalid length`);arr(x.statement_ids,`${p}.statement_ids`,1,16).forEach((q,i)=>code(q,`${p}.statement_ids[${i}]`));arr(x.comments,`${p}.comments`,0,2).forEach((q,i)=>{const c=object(q,`${p}.comments[${i}]`);keys(c,['chart_id','text','evidence_ids'],`${p}.comments[${i}]`);lit(c.chart_id,VIEW_IDS,`${p}.comments[${i}].chart_id`);const z=string(c.text,`${p}.comments[${i}].text`);if([...z].length<1||[...z].length>280)fail(`${p}.comments[${i}].text invalid length`);arr(c.evidence_ids,`${p}.comments[${i}].evidence_ids`,1,8).forEach((a,j)=>code(a,`${p}.comments[${i}].evidence_ids[${j}]`))});if(!/^[0-9a-f]{64}$/.test(string(x.render_digest,`${p}.render_digest`)))fail(`${p}.render_digest invalid digest`)}

export function validateCompanyPublicH2Schema(root:Obj):asserts root is CompanyPublicH2{
 keys(root,['contract_version','projection_digest','report_id','report_version','chart_facts_version','chart_facts_hash','snapshot_capability','projection_scope','canonical_path','indexable','checked_at','checked_date','checked_date_display','identity','narrative','block_order','blocks','coverage','sources','limitations','actions','breadcrumbs','primary_claim_cta'],'root')
 lit(root.contract_version,['company_public_h2_v1'],'contract_version');if(!/^[0-9a-f]{64}$/.test(string(root.projection_digest,'projection_digest')))fail('projection_digest invalid');if(!UUID.test(string(root.report_id,'report_id')))fail('report_id invalid');lit(root.report_version,['1','2','3'],'report_version');lit(root.chart_facts_version,['company_card_chart_facts_v1'],'chart_facts_version');if(!/^[0-9a-f]{64}$/.test(string(root.chart_facts_hash,'chart_facts_hash')))fail('chart_facts_hash invalid');lit(root.snapshot_capability,['legacy_read_only','card_v2'],'snapshot_capability');lit(root.projection_scope,['active_publication','staged_publication','latest_unpublished'],'projection_scope');if(!PATH.test(string(root.canonical_path,'canonical_path')))fail('canonical_path invalid');bool(root.indexable,'indexable');if(!UTC.test(string(root.checked_at,'checked_at')))fail('checked_at invalid');date(root.checked_date,'checked_date');string(root.checked_date_display,'checked_date_display')
 const i=object(root.identity,'identity');keys(i,['display_name','legal_full_name','short_name','inn','ogrn','kpp','registration_date','dissolution_date','status'],'identity');text(i.display_name,'identity.display_name');text(i.legal_full_name,'identity.legal_full_name');optionalText(i.short_name,'identity.short_name');if(!/^(?:[0-9]{10}|[0-9]{12})$/.test(string(i.inn,'identity.inn')))fail('identity.inn invalid');nullable(i.ogrn,'identity.ogrn',(q,p)=>{const value=string(q,p);if(value&&!/^(?:[0-9]{13}|[0-9]{15})$/.test(value))fail(`${p} invalid`)});nullable(i.kpp,'identity.kpp',(q,p)=>{const value=string(q,p);if(value&&!/^[0-9]{9}$/.test(value))fail(`${p} invalid`)});optTruthyDate(i.registration_date,'identity.registration_date');optTruthyDate(i.dissolution_date,'identity.dissolution_date');nullable(i.status,'identity.status',(q,p)=>{const s=object(q,p);keys(s,['state','code','label','effective_date'],p);lit(s.state,['active','inactive','other'],`${p}.state`);code(s.code,`${p}.code`);text(s.label,`${p}.label`);optTruthyDate(s.effective_date,`${p}.effective_date`)})
 narrative(root.narrative,'narrative');tuple(root.block_order,'block_order',16,(q,p)=>string(q,p));const b=object(root.blocks,'blocks');keys(b,['requisites','finance_f1','finance_f2','finance_f3','finance_f4','finance_f5','arbitration_a1','arbitration_a2','arbitration_a3','arbitration_a4','arbitration_a5'],'blocks');requisites(b.requisites,'blocks.requisites');nullable(b.finance_f1,'blocks.finance_f1',f1);nullable(b.finance_f2,'blocks.finance_f2',f2);nullable(b.finance_f3,'blocks.finance_f3',f3);nullable(b.finance_f4,'blocks.finance_f4',f4);nullable(b.finance_f5,'blocks.finance_f5',f5);nullable(b.arbitration_a1,'blocks.arbitration_a1',a1);nullable(b.arbitration_a2,'blocks.arbitration_a2',(q,p)=>a23(q,p,'arbitration_a2_roles'));nullable(b.arbitration_a3,'blocks.arbitration_a3',(q,p)=>a23(q,p,'arbitration_a3_outcomes'));nullable(b.arbitration_a4,'blocks.arbitration_a4',a4);nullable(b.arbitration_a5,'blocks.arbitration_a5',a5)
 arr(root.coverage,'coverage').forEach((q,n)=>{const c=object(q,`coverage[${n}]`);keys(c,['block_id','state','population_scope','total','returned','eligible','limitation_codes'],`coverage[${n}]`);string(c.block_id,`coverage[${n}].block_id`);lit(c.state,['available','available_empty','partial','missing','not_requested','failed','conflict','gate_closed','legacy_unavailable'],`coverage[${n}].state`);lit(c.population_scope,['not_applicable','complete_collection','returned_slice'],`coverage[${n}].population_scope`);for(const k of ['total','returned','eligible'] as const)nullable(c[k],`coverage[${n}].${k}`,(x,p)=>integer(x,p,0n));arr(c.limitation_codes,`coverage[${n}].limitation_codes`,0,16).forEach((x,j)=>code(x,`coverage[${n}].limitation_codes[${j}]`))})
 arr(root.sources,'sources').forEach((q,n)=>{const s=object(q,`sources[${n}]`);keys(s,['dataset','received_at','effective_at','period','normalization_version','evidence_version'],`sources[${n}]`);lit(s.dataset,['counterparty','finance','arbitration'],`sources[${n}].dataset`);if(!UTC.test(string(s.received_at,`sources[${n}].received_at`)))fail(`sources[${n}].received_at invalid`);optTruthyDate(s.effective_at,`sources[${n}].effective_at`);optionalString(s.period,`sources[${n}].period`);code(s.normalization_version,`sources[${n}].normalization_version`);code(s.evidence_version,`sources[${n}].evidence_version`)})
 arr(root.limitations,'limitations',0,128).forEach((q,n)=>{const l=object(q,`limitations[${n}]`);keys(l,['code','block_id','field_id','message'],`limitations[${n}]`);code(l.code,`limitations[${n}].code`);nullable(l.block_id,`limitations[${n}].block_id`,string);nullable(l.field_id,`limitations[${n}].field_id`,(item,path)=>{const value=string(item,path);if(value)code(item,path)});text(l.message,`limitations[${n}].message`,512)})
 tuple(root.actions,'actions',2,(q,p)=>{const a=object(q,p);keys(a,['action_id','label','path'],p);lit(a.action_id,['check_another_company','prepare_claim'],`${p}.action_id`);string(a.label,`${p}.label`);string(a.path,`${p}.path`)});tuple(root.breadcrumbs,'breadcrumbs',2,(q,p)=>{const a=object(q,p);keys(a,['label','path','current'],p);string(a.label,`${p}.label`);string(a.path,`${p}.path`);bool(a.current,`${p}.current`)});const c=object(root.primary_claim_cta,'primary_claim_cta');keys(c,['action_id','heading','desktop_copy','button_label','path'],'primary_claim_cta');lit(c.action_id,['prepare_claim'],'primary_claim_cta.action_id');lit(c.heading,['Вам задолжали?'],'primary_claim_cta.heading');lit(c.desktop_copy,['Запустите процесс взыскания прямо сейчас: создайте досудебную претензию онлайн!'],'primary_claim_cta.desktop_copy');lit(c.button_label,['Создать претензию'],'primary_claim_cta.button_label');string(c.path,'primary_claim_cta.path')
}
