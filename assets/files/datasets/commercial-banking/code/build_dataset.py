#!/usr/bin/env python3
"""Build the banking dataset release from frozen accepted inputs.

Python >=3.10, standard library only. No downloads, interpolation, or publication.
Run from any directory: python3 code/build_dataset.py
"""
from pathlib import Path
from decimal import Decimal
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
import re

ROOT = Path(__file__).resolve().parents[1]
INP, DATA, META = (ROOT / x for x in ("inputs", "data", "metadata"))
DATA.mkdir(parents=True, exist_ok=True)
META.mkdir(parents=True, exist_ok=True)
VERSION, DATE = "0.1.0", "2026-10-29"
MONEY = "million_kc_nominal"
POP_ANNUAL, POP_INCOME, POP_PANEL = "czech_lands_active_joint_stock_banks", "czech_lands_reported_bank_income", "handbook_fourteen_bank_cohort"
POP_NB, POP_NAT, POP_PRICE = "national_bank_czechoslovakia", "national_roster_joint_stock_1929", "czechoslovakia_price_context"

def read(name):
    with (INP / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def jsread(name):
    return json.loads((INP / name).read_text(encoding="utf-8"))

def number(value):
    return Decimal(str(value)) if value not in (None, "") else None

def fmt(value):
    if value is None: return ""
    if isinstance(value, bool): return str(value).lower()
    if isinstance(value, Decimal): return format(value, ".14g")
    return value

def uniq(items):
    return ";".join(sorted(set(str(x) for x in items if x not in (None, ""))))

def write(path, rows, fields=None):
    fields = fields or list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows({key: fmt(row.get(key)) for key in fields} for row in rows)

def jsonwrite(name, obj):
    (META / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

BS = read("annual_balance_sheet.csv")
PL = read("annual_income.csv")
CP = read("annual_components.csv")
BP = read("bank_panel.csv")
RAW = read("source_records.csv")
CAT = read("source_catalog.csv")
OLD_DICT = read("original_variable_dictionary.csv")
OLD_DEF = {(x["block"], x["variable"]): x for x in OLD_DICT}
SOURCE_INDEX = {r["id"]: r for r in CAT}
INPUT_MANIFEST = jsread("input_manifest.json")
assert all(hashlib.sha256((ROOT/x["input_file"]).read_bytes()).hexdigest() == x["sha256"] for x in INPUT_MANIFEST), "Frozen input checksum mismatch"

ALIASES = {
    "carried_forward_from_preceding_year": "profit_brought_forward",
    "carried_forward_to_following_year": "profit_carried_forward",
    "carried_to_reserves": "profit_to_reserves",
    "drawn_from_capital_reserves": "capital_reserve_draws",
    "taken_from_reserves_or_capital": "capital_reserve_draws",
    "total_available_distribution": "total_disposed_for_dividends_etc",
    "total_distributed": "total_disposed_for_dividends_etc",
    "write_offs_investments_and_other_combined": "writeoffs_investments_other_combined",
    "writeoffs_investments_other": "writeoffs_investments_other_combined",
    "write_offs_investments_securities": "writeoffs_securities",
    "write_offs_other_assets": "writeoffs_other_assets",
    "write_offs_premises": "writeoffs_premises",
}
RAW_LOOKUP = defaultdict(list)
for r in RAW:
    RAW_LOOKUP[(r["block"], int(r["period"]), ALIASES.get(r["variable_id"],r["variable_id"]))].append(r)

TABLES, COLUMN_SPEC, CELLS, LINEAGE = {}, {}, {}, []
LONG_TABLES = set()

def spec(table, column, description, unit="", role="measure", dtype="number", formula="", original_label="", source_column=""):
    COLUMN_SPEC[(table,column)] = dict(description=description, unit=unit, role=role, data_type=dtype, formula=formula, original_label=original_label, source_column=source_column)

def observation(table, entity, year, variable, value, *, unit=MONEY, population=POP_ANNUAL,
                status=None, kind="reported", sources=(), records=(), pages="", flags="", notes="",
                input_file="", source_column="", source_row="", original_value="", original_symbol="", formula=""):
    if status is None:
        if value in (None, ""): status = "missing_not_reported"
        elif number(value) == 0: status = "reported_zero" if kind == "reported" else "derived_zero"
        else: status = "reported" if kind == "reported" else "derived"
    key = f"{table}:{entity}:{year}:{variable}"
    sources = uniq(sources) if not isinstance(sources,str) else sources
    records = uniq(records) if not isinstance(records,str) else records
    cell = dict(observation_id=key,dataset_id=table,entity_id=entity,year=year,variable_id=variable,value=fmt(value),unit=unit,
                population_id=population,observation_type=kind,value_status=status,source_ids=sources,source_record_ids=records,
                source_pages=pages,original_symbol=original_symbol,flags=flags,notes=notes)
    assert key not in CELLS, key
    CELLS[key] = cell
    LINEAGE.append(dict(observation_id=key,input_file=input_file,source_row_id=source_row,source_column=source_column,
                        original_value=original_value,output_value=fmt(value),transformation=formula or ("copied" if kind=="reported" else "derived"),
                        source_record_ids=records,value_status=status))
    return cell

def derive(table, entity, year, variable, value, deps, formula, unit=MONEY, population=POP_ANNUAL, status=None, flags=""):
    parents=[CELLS[d] for d in deps if d in CELLS]
    return observation(table,entity,year,variable,value,unit=unit,population=population,kind="derived",status=status,
                       sources=[x for p in parents for x in p["source_ids"].split(";")],records=[x for p in parents for x in p["source_record_ids"].split(";")],
                       pages=uniq(p["source_pages"] for p in parents),flags=flags,formula=formula,source_row=uniq(deps))

def save_table(table, rows, long=False):
    TABLES[table]=rows
    write(DATA / f"{table}.csv", rows)
    if long: LONG_TABLES.add(table)

def getcell(table, entity, year, variable): return f"{table}:{entity}:{year}:{variable}"

def annual_flags(year):
    flags=[]
    if year == 1919: flags.append("deposits_include_unseparated_bank_creditors")
    if year == 1936: flags.append("income_population_22_balance_population_23")
    return ";".join(flags)

BS_COLS = list(BS[0])[1:list(BS[0]).index("broad_cash")]
PL_COLS = [k for k in PL[0] if k not in {"year","source_entries","bs_pnl_bank_counts_match","operating_surplus_before_pensions_writeoffs","rounding_residual_in_net_profit"}]
CP_COLS = [k for k in CP[0] if k not in {"year","source_entries"}]

for table, input_name, rows, columns, block, oldblock, population in [
    ("annual_balance_sheet","annual_balance_sheet.csv",BS,BS_COLS,"bank_balance","balance_sheet",POP_ANNUAL),
    ("annual_income","annual_income.csv",PL,PL_COLS,"bank_pnl","profit_loss",POP_INCOME),
    ("annual_components","annual_components.csv",CP,CP_COLS,"bank_components","components",POP_ANNUAL),
]:
    result=[]
    for row in rows:
        y=int(row["year"])
        out={"year":y,"population_id":population}
        for col in columns:
            val=row[col]
            raw=RAW_LOOKUP.get((block,y,col),[])
            matching=[x for x in raw if x["value"] != "" and val != "" and number(x["value"])==number(val)]
            relevant=matching or [x for x in raw if x["value"]==val]
            entries=[x.strip() for x in row["source_entries"].split(";")]
            source_ids=[x["source_id"] for x in relevant] or [SOURCE_INDEX[x]["source_id"] for x in entries if x in SOURCE_INDEX]
            pages=uniq(f'{x["source_id"]}:printed{x["printed_pages"]};pdf{x["pdf_pages"]}' for x in relevant)
            if not pages: pages=uniq(f'{SOURCE_INDEX[x]["source_id"]}:printed{SOURCE_INDEX[x]["printed_pages"]};pdf{SOURCE_INDEX[x]["pdf_pages"]}' for x in entries if x in SOURCE_INDEX)
            flags=annual_flags(y)
            unit="bank_count" if col=="bank_count" else MONEY
            thispop=POP_INCOME if (table=="annual_income" or (table=="annual_components" and col in {"net_interest_discounts","commissions","securities_participation_profits","sundry_profits","reserved_other_nonloss_funds_decimal","reserved_other_purposes_decimal","reserved_pension_etc_decimal_total","reserved_pension_funds_decimal"})) else population
            observation(table,"aggregate",y,col,val,unit=unit,population=thispop,sources=source_ids,records=[x["observation_id"] for x in relevant],
                        pages=pages,flags=flags,input_file="inputs/"+input_name,source_column=col,source_row=str(y),original_value=val,
                        notes="Printed values remain as transcribed. Missing components are not zero-filled.")
            out[col]=val
        out.update(source_ids=uniq(SOURCE_INDEX[x.strip()]["source_id"] for x in row["source_entries"].split(";") if x.strip() in SOURCE_INDEX),
                   source_entry_ids=uniq(x.strip() for x in row["source_entries"].split(";")),flags=annual_flags(y))
        if table=="annual_balance_sheet": out.update(cash_definition=row["cash_definition"],deposit_definition=row["deposit_definition"])
        if table=="annual_income": out.update(balance_bank_count=next(x["bank_count"] for x in BS if x["year"]==str(y)),income_balance_counts_match=(y!=1936))
        result.append(out)
    save_table(table,result,True)
    for col in columns:
        desc=OLD_DEF.get((oldblock,col),{})
        spec(table,col,desc.get("definition_or_formula", "Published source category; retained separately without infilling."),unit="bank_count" if col=="bank_count" else MONEY,
             original_label=desc.get("label",col.replace("_"," ")),source_column=col)

# A compact convenience view. Its facts are linked to the detail tables; it is
# excluded from the canonical tidy count so repeated wide views are not counted.
CORE_MAP = {
 "balance_bank_count":("annual_balance_sheet","bank_count"),"income_bank_count":("annual_income","bank_count"),
 "total_assets":("annual_balance_sheet","total_assets"),"loans_advances":("annual_balance_sheet","loans_advances"),
 "bills_discounted":("annual_balance_sheet","bills_discounted"),"securities":("annual_balance_sheet","investments_securities"),
 "participations":("annual_balance_sheet","participations"),"premises":("annual_balance_sheet","premises"),"sundry_assets":("annual_balance_sheet","sundry_assets"),
 "paid_capital":("annual_balance_sheet","capital_paid"),"loss_covering_reserves":("annual_balance_sheet","reserve_funds"),
 "balance_sheet_profit":("annual_balance_sheet","pnl_balance"),"reported_deposits_total":("annual_balance_sheet","total_deposits"),
 "due_to_banks":("annual_balance_sheet","due_to_banks"),"sundry_liabilities":("annual_balance_sheet","sundry_liabilities"),
 "net_interest":("annual_components","net_interest_discounts"),"commissions":("annual_components","commissions"),
 "gross_profits":("annual_income","gross_profits"),"operating_expenses":("annual_income","expenses_total"),
 "net_profit_loss":("annual_income","net_profit_loss"),"writeoffs":("annual_income","writeoffs_total"),"dividends":("annual_income","dividends"),
}
CORE_ORDER=["year","population_id","balance_bank_count","income_bank_count","total_assets","loans_advances","bills_discounted","loans_and_bills","identified_sundry_loans","extended_credit","broad_cash","securities","participations","premises","sundry_assets","paid_capital","loss_covering_reserves","capital_and_reserves","balance_sheet_profit","reported_deposits_total","total_deposits","due_to_banks","sundry_liabilities","net_interest","commissions","gross_profits","operating_expenses","net_profit_loss","writeoffs","dividends","deposits_comparable","income_balance_counts_match","flags","source_ids","source_entry_ids"]
CORE=[]
bybs={int(x["year"]):x for x in BS}
bycp={int(x["year"]):x for x in CP}
for y in range(1919,1938):
    r={"year":y,"population_id":POP_ANNUAL}
    for target,(tab,col) in CORE_MAP.items():
        cell=CELLS[getcell(tab,"aggregate",y,col)]
        r[target]=cell["value"]
        observation("annual_aggregate","aggregate",y,target,cell["value"],unit=cell["unit"],population=cell["population_id"],
                    status=cell["value_status"],sources=cell["source_ids"],records=cell["source_record_ids"],pages=cell["source_pages"],flags=cell["flags"],
                    source_row=cell["observation_id"],formula="convenience_view_of:"+cell["observation_id"])
        base=COLUMN_SPEC[(tab,col)]
        spec("annual_aggregate",target,base["description"],unit=base["unit"],original_label=base["original_label"],source_column=f"{tab}.{col}")
    formulas={
        "loans_and_bills":([("annual_balance_sheet","loans_advances"),("annual_balance_sheet","bills_discounted")],"loans_advances + bills_discounted"),
        "capital_and_reserves":([("annual_balance_sheet","capital_paid"),("annual_balance_sheet","reserve_funds")],"capital_paid + reserve_funds"),
    }
    if bybs[y]["cash_plus_other_cash_like"]:
        formulas["broad_cash"]=([("annual_balance_sheet","cash_plus_other_cash_like")],"published combined cash category")
    else: formulas["broad_cash"]=([("annual_balance_sheet","cash"),("annual_balance_sheet","other_cash_like")],"cash + other_cash_like")
    if bycp[y]["mortgage_municipal_railway_loans"]:
        formulas["identified_sundry_loans"]=([("annual_components","mortgage_municipal_railway_loans")],"published combined sundry-loan category")
    else: formulas["identified_sundry_loans"]=([("annual_components","mortgage_loans"),("annual_components","municipal_railway_loans")],"mortgage_loans + municipal_railway_loans; both required")
    for var,(inputs,formula) in formulas.items():
        deps=[getcell(t,"aggregate",y,c) for t,c in inputs]
        vals=[number(CELLS[d]["value"]) for d in deps]
        val=sum(vals) if all(v is not None for v in vals) else None
        r[var]=fmt(val)
        derive("annual_aggregate","aggregate",y,var,val,deps,formula,flags=annual_flags(y))
        spec("annual_aggregate",var,formula+". No missing component is treated as zero.",unit=MONEY,formula=formula)
    r["extended_credit"]=fmt(number(r["loans_and_bills"])+number(r["identified_sundry_loans"])) if r["loans_and_bills"] and r["identified_sundry_loans"] else ""
    derive("annual_aggregate","aggregate",y,"extended_credit",r["extended_credit"],[getcell("annual_aggregate","aggregate",y,x) for x in ("loans_and_bills","identified_sundry_loans")],"loans_and_bills + identified_sundry_loans",flags=annual_flags(y))
    spec("annual_aggregate","extended_credit","Loans, bills and identified mortgage/municipal/railway assets; includes bank claims and is not isolated nonfinancial credit.",unit=MONEY,formula="loans_and_bills + identified_sundry_loans")
    r["total_deposits"]="" if y==1919 else r["reported_deposits_total"]
    derive("annual_aggregate","aggregate",y,"total_deposits",r["total_deposits"],[getcell("annual_balance_sheet","aggregate",y,"total_deposits")],"reported_deposits_total if year >= 1920; otherwise unavailable",status="not_comparable" if y==1919 else "derived",flags=annual_flags(y))
    spec("annual_aggregate","total_deposits","Comparable reported deposit total, excluding separately classified bank creditors; blank in 1919. The original 1919 amount remains in reported_deposits_total.",unit=MONEY,formula="reported_deposits_total for 1920-1937; blank in 1919")
    r.update(deposits_comparable=y!=1919,income_balance_counts_match=y!=1936,flags=annual_flags(y))
    r["source_ids"]=uniq(s for c in CORE_MAP for s in CELLS[getcell("annual_aggregate","aggregate",y,c)]["source_ids"].split(";"))
    r["source_entry_ids"]=uniq(x for rows in (BS,PL,CP) for row in rows if row["year"]==str(y) for x in (z.strip() for z in row["source_entries"].split(";")))
    CORE.append({k:r.get(k,"") for k in CORE_ORDER})
save_table("annual_aggregate",CORE)

# Panel labels remain source-specific; no equation with League deposits or bank debt.
PANEL_MAP={"total_assets":"total_assets","cash":"cash_source_hotovosti","bills":"bills_source_smenky","securities":"securities_source_efekty","participations":"participations_source_ucasti","debtors":"debtors_source_dluznici","premises":"premises_source_budovy","other_assets":"other_assets_source_ruzne","paid_capital":"capital","published_reserves":"published_reserves","other_funds":"other_funds_source_fondy","source_deposits":"deposits_source_vklady","general_creditors":"general_creditors_source_veritele","other_liabilities":"other_liabilities_source_ruzne","profit_carried_forward":"profit_carried_forward","reported_net_profit":"reported_net_profit","net_interest":"net_interest_source_urok_saldo","commissions":"fees_source_odmeny","other_income":"other_income_source_ruzne_zisky","overheads_nonstaff":"overheads_nonstaff","overheads_staff":"overheads_staff","taxes":"taxes","depreciation":"depreciation","other_losses":"other_losses","issue_loans":"issue_loans_source_emisni_pujcky","bonds_issued":"bonds_source_dluhopisy","stabilization_fund":"stabilization_fund_source_stab_fond"}
PANEL_SOURCE_LABEL={"cash":"hotovosti","bills":"směnky","securities":"efekty","participations":"účasti","debtors":"dlužníci","premises":"budovy","other_assets":"různé (aktiva)","paid_capital":"akciový kapitál","published_reserves":"reservy","other_funds":"fondy","source_deposits":"vklady","general_creditors":"věřitelé","other_liabilities":"různé (pasiva)","net_interest":"úrokové saldo","commissions":"odměny","issue_loans":"emisní půjčky","bonds_issued":"dluhopisy","stabilization_fund":"stabilisační fond"}
PANEL_NOTES={
 "total_assets":"Published annual balance-sheet total; Moravská 1933 component discrepancy is retained.",
 "cash":"Source hotovosti; Sporobanka includes Treasury bills, so this is not vault cash or central-bank reserves alone.",
 "bills":"Source bills; combined with debtors only as a lending-related aggregate, not exclusively nonfinancial credit.",
 "securities":"Source securities; Všeobecná družstevní includes participations in this line.",
 "participations":"Separately reported participation holdings; absent as a separate line for Všeobecná družstevní.",
 "debtors":"Source debtors; counterparty sectors and interbank claims are not separately identified.",
 "paid_capital":"Published paid share capital; separate from published reserves and other funds.",
 "published_reserves":"Published reserve line. Hidden reserves, separate stabilization funds and other funds are not mechanically added.",
 "source_deposits":"Source vklady; Legiobanka includes mortgage borrowing. Not harmonized to the League deposit category.",
 "general_creditors":"Source věřitelé, general creditors. Not an interbank-only funding measure.",
 "net_interest":"Published interest balance after interest costs; dividing by closing assets measures income intensity, not conventional net interest margin.",
 "commissions":"Source odměny, fee/commission income; a yearly flow.",
 "stabilization_fund":"Legiobanka's separate stabilization fund; not pooled with published reserves. Dashes after utilization remain missing markers.",
 "issue_loans":"Separately reported issue-related loans; not added twice to debtors.",
 "bonds_issued":"Separately reported bond liabilities, not equity.",
}
BANK_SPEC={'agrarni':((65,0),(65,1),(65,2)),'lander':((66,0),(66,1),(67,0)),'ceska':((68,0),(68,1),(68,2)),'union':((70,0),(70,1),(70,2)),'escomp':((72,0),(73,0),(73,1)),'prumyslova':((74,0),(74,1),(75,0)),'moravska':((76,0),(76,1),(76,2)),'plzenska':((83,0),(83,1),(83,2)),'sporobanka':((86,0),(86,1),(86,2)),'zivno':((88,0),(88,1),(88,2)),'anglo':((229,0),(229,1),(230,0)),'legio':((231,0),(231,1),(231,2)),'deutagr':((232,0),(232,1),(233,0)),'vseobdruz':((234,3),(235,0),(235,1))}
A8=['cash','bills','securities','participations','debtors','premises','other_assets','total_assets']
L8=['paid_capital','published_reserves','other_funds','source_deposits','general_creditors','other_liabilities','profit_carried_forward','reported_net_profit']
I8=['net_interest','commissions','other_income','overheads_nonstaff','overheads_staff','taxes','depreciation','other_losses']
TOKENS={}
rawtables=jsread("bank_raw_table_rows.json")
for bank,groups in BANK_SPEC.items():
    for g,(page,group) in enumerate(groups):
        for year,tokens in rawtables[str(page)][group]:
            if g==0: names={7:[x for x in A8 if x!='participations'],8:A8,9:A8[:5]+['issue_loans']+A8[5:]}[len(tokens)]
            elif g==1: names={7:['paid_capital','published_reserves','source_deposits','general_creditors','other_liabilities','reported_net_profit','profit_carried_forward'],8:L8,9:L8[:3]+['bonds_issued']+L8[3:]}[len(tokens)]
            else: names=I8
            for col,token in zip(names,tokens):
                if bank=='legio' and col=='other_funds': col='stabilization_fund'
                TOKENS[(bank,int(year),col)]=(token,page)
PANEL=[]
for source in BP:
    bank,y=source['bank_id'],int(source['year'])
    flags=[]
    if bank=='moravska' and y==1933: flags.append('asset_components_below_reported_total_20_million')
    if bank=='sporobanka':
        flags.append('savings_bank_central_institution')
        if y>=1935: flags.append('cash_includes_treasury_bills')
        if y==1937: flags.append('savings_bank_mandate_expansion')
    if bank=='legio': flags.append('source_deposits_include_mortgage_borrowing')
    if bank=='vseobdruz': flags.append('securities_include_participations')
    out={'bank_id':bank,'bank_name':source['bank'],'year':y,'population_id':POP_PANEL}
    for col,old in PANEL_MAP.items():
        val=source[old];token,page=TOKENS.get((bank,y,col),('', ''))
        state=None
        if not val: state='source_dash' if token.strip() in ('-','—') else 'not_separately_reported'
        original = re.sub(r'\d\)$','',token.strip()).replace(' ','')
        if val:
            parsed=number(original.replace('.',''))/1000 if bank=='vseobdruz' else number(''.join(original.split('.')[:-1])+'.'+original.split('.')[-1]) if original.count('.')>1 else number(original)
            assert parsed==number(val),(bank,y,col,parsed,val)
        observation('bank_panel',bank,y,col,val,population=POP_PANEL,status=state,sources=[source['source_id']],records=[f'kaspar:{bank}:{y}:{col}'] if token else [],
                    pages=f'Kašpar digital PDF {page}' if page else '',flags=';'.join(flags),notes=PANEL_NOTES.get(col,''),input_file='inputs/bank_panel.csv',source_column=old,source_row=f'{bank}:{y}',
                    original_value=token,original_symbol='-' if token.strip() in ('-','—') else '',formula='source token converted from thousand Kč to million Kč' if bank=='vseobdruz' else 'source token normalized; note marker removed; numerical amount unchanged')
        out[col]=val
    out.update(asset_pdf_page=source['asset_pdf_page'],liability_pdf_page=source['liability_pdf_page'],income_pdf_page=source['income_pdf_page'],source_id=source['source_id'],source_url=source['source_url'],source_original_unit=source['source_original_unit'],source_edition=source['source_edition'],original_annual_report_verified=False,asset_component_residual=source['asset_component_sum_minus_total'],category_notes=source['category_note'],flags=';'.join(flags))
    PANEL.append(out)
save_table('bank_panel',PANEL,True)
for col,old in PANEL_MAP.items(): spec('bank_panel',col,PANEL_NOTES.get(col,'Published '+col.replace('_',' ')+' category, retained separately without imputation.'),unit=MONEY,original_label=PANEL_SOURCE_LABEL.get(col,col.replace('_',' ')),source_column=old)

# Derived indicators use end-year assets, full stated denominators and explicit exclusions.
ANNUAL_RATIO_MAP={'capital_assets_pct':('capital_and_reserves','total_assets'),'loans_bills_assets_pct':('loans_and_bills','total_assets'),'extended_credit_assets_pct':('extended_credit','total_assets'),'cash_assets_pct':('broad_cash','total_assets'),'securities_assets_pct':('securities','total_assets'),'participations_assets_pct':('participations','total_assets'),'deposits_assets_pct':('total_deposits','total_assets'),'bank_creditors_assets_pct':('due_to_banks','total_assets'),'loans_bills_deposits_pct':('loans_and_bills','total_deposits'),'net_interest_assets_pct':('net_interest','total_assets'),'commissions_assets_pct':('commissions','total_assets'),'net_profit_assets_pct':('net_profit_loss','total_assets')}
INDEX_MAP={'assets':'total_assets','loans_bills':'loans_and_bills','deposits':'total_deposits','capital_reserves':'capital_and_reserves'}
AR=[];corey={r['year']:r for r in CORE}
for row in CORE:
    y=row['year'];out={'year':y,'population_id':POP_ANNUAL}
    for col,(num,den) in ANNUAL_RATIO_MAP.items():
        invalid=y==1936 and num in {'net_interest','commissions','net_profit_loss'}
        a,b=number(row[num]),number(row[den]); val=None if invalid or a is None or b in (None,0) else 100*a/b
        status='not_comparable' if invalid or (y==1919 and ('deposits' in num or 'deposits' in den or num=='due_to_banks')) else 'missing_prerequisite' if val is None else None
        out[col]=fmt(val)
        formula=f'100 * {num} / {den}; closing-year denominator; suppress known population or category mismatch'
        derive('annual_ratios','aggregate',y,col,val,[getcell('annual_aggregate','aggregate',y,v) for v in (num,den)],formula,unit='percent',status=status,flags=row['flags'])
        spec('annual_ratios',col,formula+'. Income ratios are intensities, not conventional net interest margins.',unit='percent',formula=formula)
    for label,var in INDEX_MAP.items():
        col=label+'_index_1930_100';a,b=number(row[var]),number(corey[1930][var]);val=100*a/b if a is not None else None
        out[col]=fmt(val);form=f'100 * {var}[year] / {var}[1930]'
        derive('annual_ratios','aggregate',y,col,val,[getcell('annual_aggregate','aggregate',yr,var) for yr in (y,1930)],form,unit='index_1930_100',status='not_comparable' if y==1919 and var=='total_deposits' else None,flags=row['flags'])
        spec('annual_ratios',col,form,unit='index_1930_100',formula=form)
    for label,var in INDEX_MAP.items():
        col=label+'_growth_pct';prev=corey.get(y-1);a=number(row[var]);b=number(prev[var]) if prev else None;val=100*(a/b-1) if a is not None and b not in (None,0) else None
        out[col]=fmt(val);form=f'100 * ({var}[year] / {var}[year-1] - 1); changing annual population'
        derive('annual_ratios','aggregate',y,col,val,[getcell('annual_aggregate','aggregate',yr,var) for yr in (y,y-1)],form,unit='percent',status='not_comparable' if var=='total_deposits' and y<=1920 else 'missing_prerequisite' if val is None else None,flags=row['flags'])
        spec('annual_ratios',col,form,unit='percent',formula=form)
    out['flags']=row['flags'];AR.append(out)
save_table('annual_ratios',AR,True)

BR=[];panelkeys={(r['bank_id'],r['year']):r for r in PANEL}
PANEL_RATIO_MAP={'capital_assets_pct':'capital_and_reserves','debtors_bills_assets_pct':'debtors_and_bills','cash_assets_pct':'cash','securities_assets_pct':'securities','source_deposits_assets_pct':'source_deposits','general_creditors_assets_pct':'general_creditors','net_interest_assets_pct':'net_interest','commissions_assets_pct':'commissions'}
for r in PANEL:
    bank,y=r['bank_id'],r['year'];o={'bank_id':bank,'bank_name':r['bank_name'],'year':y,'population_id':POP_PANEL}
    for col,vars in [('capital_and_reserves',('paid_capital','published_reserves')),('debtors_and_bills',('debtors','bills'))]:
        val=sum(number(r[x]) for x in vars);o[col]=fmt(val);form=' + '.join(vars)
        derive('bank_ratios',bank,y,col,val,[getcell('bank_panel',bank,y,x) for x in vars],form,population=POP_PANEL,flags=r['flags']);spec('bank_ratios',col,form,unit=MONEY,formula=form)
    for col,var in PANEL_RATIO_MAP.items():
        val=100*number(o.get(var,r.get(var)))/number(r['total_assets']);o[col]=fmt(val);form=f'100 * {var} / total_assets; closing-year assets'
        derive('bank_ratios',bank,y,col,val,[getcell('bank_ratios' if var in o else 'bank_panel',bank,y,var),getcell('bank_panel',bank,y,'total_assets')],form,unit='percent',population=POP_PANEL,flags=r['flags'])
        spec('bank_ratios',col,form+'. Source categories remain bank-specific; income ratios are intensities, not NIM.',unit='percent',formula=form)
    for label,var in {'assets':'total_assets','capital_reserves':'capital_and_reserves','debtors_bills':'debtors_and_bills','net_interest':'net_interest','commissions':'commissions'}.items():
        base=panelkeys[(bank,1933)];den=(number(base['paid_capital'])+number(base['published_reserves'])) if var=='capital_and_reserves' else (number(base['debtors'])+number(base['bills'])) if var=='debtors_and_bills' else number(base[var])
        val=100*number(o.get(var,r.get(var)))/den;col=label+'_index_1933_100';o[col]=fmt(val);tab='bank_ratios' if var in ('capital_and_reserves','debtors_and_bills') else 'bank_panel';form=f'100 * {var}[year] / {var}[1933]'
        derive('bank_ratios',bank,y,col,val,[getcell(tab,bank,yr,var) for yr in (y,1933)],form,unit='index_1933_100',population=POP_PANEL,flags=r['flags']);spec('bank_ratios',col,form,unit='index_1933_100',formula=form)
    o['flags']=r['flags'];BR.append(o)
save_table('bank_ratios',BR,True)

# National Bank context is a separate institution and is never added to the
# commercial-bank aggregate or the named-bank panel.
NB=[]
for r in read('central_bank_context.csv'):
    y=int(r['year']);sid='LON_CB_1938' if y==1930 else 'LON_CB_1939'
    pages='printed61;pdf63' if y==1930 else 'printed47;pdf49'
    o={'year':y,'population_id':POP_NB}
    for col in ['discounted_bills','discounted_securities','advances_on_collateral','total_assets','notes_in_circulation']:
        o[col]=r[col]
        observation('central_bank_context','national_bank',y,col,r[col],population=POP_NB,sources=[sid],records=[f'nb:{y}:{col}'],pages=pages,input_file='inputs/central_bank_context.csv',source_column=col,source_row=str(y),original_value=r[col],notes='National Bank accounts; not a commercial-bank population or a complete interbank reconciliation.')
        spec('central_bank_context',col,'National Bank '+col.replace('_',' ')+'. Separate institutional context; no consolidation with commercial banks.',unit=MONEY,source_column=col)
    o.update(source_id=sid,source_pages=pages,flags='separate_central_bank_population')
    NB.append(o)
save_table('central_bank_context',NB,True)

WPI={int(r['balance_sheet_year']):r for r in read('wpi_annual.csv')}
CPI_DOC=jsread('cpi_cell_provenance.json')
CPI={r['year']:r for r in CPI_DOC['cells']}
PRICE=[]
WPI_MAP={'wpi_available_months':'available_months_in_calendar_year','wpi_annual_mean':'full_year_monthly_mean','wpi_december_first':'december_first_observation','wpi_year_end_proxy':'year_end_proxy_following_january_first','wpi_year_end_proxy_1929_100':'year_end_proxy_index_end1929_100'}
for y in range(1919,1939):
    w,c=WPI.get(y,{}),CPI.get(y,{})
    flags=[]
    if not w:flags.append('wpi_outside_frozen_extract')
    elif w.get('available_months_in_calendar_year')!='12':flags.append('wpi_incomplete_calendar_year')
    if c.get('value') is None:flags.append('cpi_not_available')
    o={'year':y,'population_id':POP_PRICE}
    for col,old in WPI_MAP.items():
        val=w.get(old,'');unit='month_count' if col=='wpi_available_months' else 'index_end_1929_100' if col.endswith('1929_100') else 'index_july_1914_100'
        kind='derived' if col in {'wpi_annual_mean','wpi_year_end_proxy_1929_100','wpi_available_months'} else 'reported'
        formula={'wpi_annual_mean':'arithmetic mean of twelve monthly first-of-month observations; no partial-year mean','wpi_year_end_proxy_1929_100':'100 * following-January-first WPI / 862 (1 January 1930)','wpi_available_months':'count of available first-of-month observations in frozen calendar year'}.get(col,'unchanged source observation; no date interpolation')
        observation('price_context','price_context',y,col,val,unit=unit,population=POP_PRICE,kind=kind,sources=['WPI_READER_20261023'] if w else [],records=[f'wpi_annual:{y}:{old}'] if w else [],pages=w.get('year_end_proxy_source_date','') if 'year_end_proxy' in col else '',flags=';'.join(flags),input_file='inputs/wpi_annual.csv',source_column=old,source_row=str(y),original_value=val,formula=formula)
        o[col]=val;spec('price_context',col,formula+'. WPI context has broader geographical/conceptual scope than the bank sample.',unit=unit,formula=formula,source_column=old)
    val=c.get('value');o['cpi_source_index']=fmt(val)
    observation('price_context','price_context',y,'cpi_source_index',val,unit='index_source_base_unspecified',population=POP_PRICE,sources=['CPI_LJUNGBERG_WORKBOOK'],records=[f'cpi:{c.get("cell","")}'],pages=c.get('cell',''),flags=';'.join(flags),input_file='inputs/cpi_cell_provenance.json',source_column='value',source_row=c.get('cell',''),original_value=val,notes='The frozen extract does not establish the original index base or within-year timing. Floating-point values are retained as extracted.')
    rebased=100*number(val)/number(CPI[1929]['value']) if val is not None else None;o['cpi_1929_100']=fmt(rebased)
    spec('price_context','cpi_source_index','Unchanged annual CPI workbook value. The original index base and within-year timing are not specified in the frozen provenance extract.',unit='index_source_base_unspecified',source_column='cells.value')
    spec('price_context','cpi_1929_100','Release-derived rebasing; 100 times the source index divided by its 1929 value. This does not assert that 1929 was the source publication base.',unit='index_1929_100',formula='100 * cpi_source_index / cpi_source_index[1929]')
    o.update(wpi_proxy_source_date=w.get('year_end_proxy_source_date',''),cpi_source_cell=c.get('cell',''),source_ids=uniq(['CPI_LJUNGBERG_WORKBOOK']+(['WPI_READER_20261023'] if w else [])),flags=';'.join(flags))
    PRICE.append(o)
for o in PRICE:
    y=o['year']
    derive('price_context','price_context',y,'cpi_1929_100',o['cpi_1929_100'],[getcell('price_context','price_context',yr,'cpi_source_index') for yr in (y,1929)],'100 * cpi_source_index / source 1929 value; release rebasing',unit='index_1929_100',population=POP_PRICE,status='missing_prerequisite' if o['cpi_1929_100']=='' else None,flags=o['flags'])
save_table('price_context',PRICE,True)

# Preserve the accepted roster, including its historically audited dash-to-zero
# accounting convention; those cells are explicitly NOT described as printed zeros.
CROSS=[]
for r in read('institution_crosswalk_1929.csv'):
    o=dict(r);o['national_year']=int(r['national_year']);o['included_in_1933_1937_panel']=r['included_in_1933_1937_panel']=='1'
    o['population_id']=POP_NAT;o['zero_value_convention']='accepted transcription uses zero for printed dashes; not a printed numerical zero'
    for col in [x for x in r if x.endswith('_thousand_kc')]:
        state='source_dash_accounted_as_zero' if number(r[col])==0 else 'reported'
        observation('institution_crosswalk_1929',r['national_bank_id'],1929,col,r[col],unit='thousand_kc_nominal',population=POP_NAT,status=state,sources=['NATIONAL_1932'],records=[f'nat1929:{r["national_bank_id"]}:{col}'],pages='printed259;pdf_part4_7',flags='source_dash_zero_convention' if state!='reported' else '',input_file='inputs/institution_crosswalk_1929.csv',source_column=col,source_row=r['national_bank_id'],original_value=r[col],original_symbol='-' if state!='reported' else '',notes=o['zero_value_convention'] if state!='reported' else '')
        spec('institution_crosswalk_1929',col,{'paid_capital_thousand_kc':'Paid share capital in national table X5.','loss_cover_reserves_thousand_kc':'Loss-covering reserve funds in X5, excluding earmarked nonloss funds.','book_and_cash_certificate_deposits_thousand_kc':'Passbook and cash-certificate deposits, not total deposits in the League reclassification.','creditors_thousand_kc':'General creditors, including bank creditors, other current accounts and mortgage borrowing.','own_bonds_thousand_kc':'Own-issued debt securities; accepted dashes-as-zero convention is flagged.'}[col],unit='thousand_kc_nominal',source_column=col)
    CROSS.append(o)
save_table('institution_crosswalk_1929',CROSS,True)

COVER=[]
for r in read('coverage_1929.csv'):
    o=dict(r);o['measure']=r['measure'].removesuffix('_thousand_kc');o['year']=int(r['year']);o['unit']='institution_count' if r['measure']=='institutions' else MONEY;o['population_id']=POP_NAT
    for col in ['national_22_total','matched_14_total','unmatched_8_total','matched_share_percent']:
        unit='percent' if col=='matched_share_percent' else o['unit']
        observation('coverage_1929',o['measure'],1929,col,r[col],unit=unit,population=POP_NAT,kind='derived',sources=['NATIONAL_1932','KASPAR_1938_1939_RETYPED_2006'],records=[f'nat1929:coverage:{r["measure"]}'],pages='national printed259-260; handbook identity pages in crosswalk',input_file='inputs/coverage_1929.csv',source_row=r['measure'],source_column=col,original_value=r[col],formula='source-internal sum/count or matched/all share; 1929 roster only',notes='A dated 1929 footprint, not later-year asset coverage. National published dashes have the accepted zero-accounting convention.')
        spec('coverage_1929',col,'1929 national-roster '+col.replace('_',' ')+'. No later population equivalence is assumed.',unit='row_unit' if col!='matched_share_percent' else 'percent',formula='source-internal roster aggregation')
    COVER.append(o)
save_table('coverage_1929',COVER,True)

NAMES={r['bank_id']:r['bank_name'] for r in PANEL}
EVENT_TYPES={'escomp':'published_to_hidden_reserve_transfer','lander':'provision_reclassification','legio':'stabilization_fund_utilization','ceska':'opening_balance_restatement','plzenska':'opening_balance_restatement'}
EVENT_TEXT={
 'escomp':('Transfer from published to hidden reserves.','Gross reclassification; no automatic addition to aggregate equity. Cancellation of own shares separately reduces capital from 170 to 130 million Kč.'),
 'lander':('Earmarked provision for current-account debtors moved to other liabilities.','The 46 million transfer is not identical to the 45.9 million net fall in published reserves; other movements offset part of the transfer.'),
 'legio':('Separate stabilization fund used on 1 January 1935 to reduce property, inventory and participation values.','The separate fund was 35 million in 1933 and 1934 and is a dash thereafter. Explicit published reserves remained 65 million. Its League reserve classification is unestablished.'),
 'ceska':('Restabilization opening balance reduced reserves from 10.0 to 9.3 million.','The 0.7 million amount is the calculated opening adjustment; closing 1935 reserves were 9.4 million. Opening and closing values are not substituted.'),
 'plzenska':('Restabilization opening balance reduced reserves from 19.3 to 18.4 million.','The 0.9 million amount is the calculated opening adjustment; closing 1935 reserves were 19.8 million. Positive endpoint reserve growth can coexist with this adjustment.'),
}
EVENTS=[]
for r in read('reserve_events.csv'):
    bank,y=r['bank_id'],int(r['year']);event_id=f'{bank}_{y}_{EVENT_TYPES[bank]}'
    o={'event_id':event_id,'bank_id':bank,'bank_name':NAMES[bank],'year':y,'event_date':f'{y}-01-01' if bank in {'legio','ceska','plzenska'} else '', 'event_type':EVENT_TYPES[bank], 'amount_million_kc':r['amount_million_kc'],'amount_status':'derived_opening_adjustment' if bank in {'ceska','plzenska'} else 'reported_transfer_or_utilization', 'published_reserves_previous_year':r['published_reserves_previous_year'],'published_reserves_year_end':r['published_reserves_event_year'], 'published_reserves_opening_after_adjustment': '9.3' if bank=='ceska' else '18.4' if bank=='plzenska' else '', 'event_description':EVENT_TEXT[bank][0],'interpretation':EVENT_TEXT[bank][1], 'source_id':'KASPAR_1938_1939_RETYPED_2006','source_pdf_pages':r['source_pdf_pages'],'original_annual_report_verified':False,'population_id':POP_PANEL}
    for col in ['amount_million_kc','published_reserves_previous_year','published_reserves_year_end','published_reserves_opening_after_adjustment']:
        val=o[col];kind='derived' if col=='amount_million_kc' and bank in {'ceska','plzenska'} else 'reported'
        observation('reserve_events',event_id,y,col,val,population=POP_PANEL,kind=kind,status='not_applicable' if val=='' else None,sources=[o['source_id']],records=[f'event:{event_id}:{col}'],pages='Kašpar digital PDF '+r['source_pdf_pages'],input_file='inputs/reserve_events.csv',source_row=bank+':'+str(y),source_column='published_reserves_event_year' if col=='published_reserves_year_end' else col,original_value=val,formula='10.0 - 9.3' if kind=='derived' and bank=='ceska' else '19.3 - 18.4' if kind=='derived' else '',notes=EVENT_TEXT[bank][1])
        spec('reserve_events',col,'Event-account '+col.replace('_',' ')+'. Dates and opening versus closing positions are explicit; amounts are not automatically additive to aggregate equity.',unit=MONEY,source_column=col)
    EVENTS.append(o)
save_table('reserve_events',EVENTS,True)

# Source-level observations retain the accepted selected-record ledger, including
# original labels and unused auxiliary observations. They are not a second
# analytic sample and are excluded from the canonical analytic count.
UNIT_MAP={'mil. Kč':MONEY,'počet':'count','bank':'bank_count','US cent / Kč':'us_cents_per_kc','CHF / Kč':'chf_per_kc'}
SOURCE_OBS=[]
for r in RAW:
    o={'source_record_id':r['observation_id'],'source_entry_id':r['entry_id'],'source_id':r['source_id'],'publication_year':r['publication_year'],'source_block':r['block'],'year':r['period'],'source_variable_id':r['variable_id'],'original_variable_label':r['variable'],'value':r['value'],'unit':UNIT_MAP[r['unit']],'original_unit':r['unit'],'value_status':'reported_zero' if r['value'] and number(r['value'])==0 else 'reported' if r['value'] else 'missing_not_reported','original_symbol':r['original_symbol'],'original_note':r['note'],'printed_pages':r['printed_pages'],'pdf_pages':r['pdf_pages'],'population_id':POP_INCOME if r['block']=='bank_pnl' else POP_ANNUAL,'original_frequency':r['frequency']}
    SOURCE_OBS.append(o)
save_table('source_observations',SOURCE_OBS)

# Metadata describes original source locations without inventing download URLs.
source_info={}
SOURCE_TITLES={
 'LON_CB_1931':'Memorandum on Commercial Banks, 1913–1929',
 'LON_CB_1934':'Commercial Banks, 1925–1933',
 'LON_CB_1935':'Commercial Banks, 1929–1934',
 'LON_CB_1938':'Money and Banking 1937/38, Volume II: Commercial and Central Banks',
 'LON_CB_1939':'Money and Banking 1938/39, Volume II: Commercial and Central Banks',
}
for entry in CAT:
    sid=entry['source_id']
    if sid not in source_info:
        source_info[sid]={'source_id':sid,'title':SOURCE_TITLES[sid],'publication_year':entry['publication_year'],'creator':'League of Nations','source_type':'historical_publication_scan','source_url':'','local_source_locator':entry['source_file'],'consulted_edition':'User-supplied historical PDF scan','verification_scope':'Accepted source table transcription, with visual verification recorded in the original source catalogue.','data_role':'Commercial-bank balance sheets, income and components','access_note':'Original PDF is not required for the offline CSV rebuild and is not redistributed here.'}
source_info['LON_CB_1938']['data_role']+='; National Bank context for 1930'
source_info['LON_CB_1939']['data_role']+='; National Bank context for 1929 and 1931-1937'
source_info.update({
 'KASPAR_1938_1939_RETYPED_2006':{'source_id':'KASPAR_1938_1939_RETYPED_2006','title':'Československé bursovní papíry 1938–1939 [Czechoslovak Stock-Exchange Securities, 1938–1939]','publication_year':1938,'creator':'Josef Kašpar','source_type':'modern_retyping_of_historical_handbook','source_url':'https://www.securityprinting.org/texty/1938_1939/csbp_1938_1939.pdf','local_source_locator':'kaspar1938_1939.pdf','consulted_edition':'Modern retyping; PDF metadata 2006','verification_scope':'Twenty account-table pages visually checked in this edition. Original bank annual-report facsimiles have not been independently verified.','data_role':'Fourteen-bank panel, reserve events and institutional identities','access_note':'Source page numbers refer to the digital retyping, not verified original-print pagination.'},
 'NATIONAL_1932':{'source_id':'NATIONAL_1932','title':'Statistická příručka republiky Československé IV [Statistical Handbook of the Czechoslovak Republic, IV]','publication_year':1932,'creator':'Státní úřad statistický','source_type':'historical_publication_scan','source_url':'','local_source_locator':'Statistická příručka Československé republiky 1932 - Cast 4(2).pdf','consulted_edition':'User-supplied original scan, part 4, PDF pages 7-9 / printed pages 259-261','verification_scope':'Named 1929 roster and aggregate controls visually checked; five column totals reconcile.','data_role':'1929 institution crosswalk, balance categories and footprint','access_note':'Accepted national CSV uses zero for printed dashes; public observation status identifies that convention.'},
 'WPI_READER_20261023':{'source_id':'WPI_READER_20261023','title':'Czechoslovak National Bank monthly price data: revised reader edition','publication_year':2026,'creator':'Adam Dittrich; underlying National Bank monthly reports','source_type':'accepted_research_reader_extract','source_url':'https://adamdittrich.github.io/assets/files/datasets/fsi/data/monthly_raw_data.csv','local_source_locator':'inputs/wpi_annual.csv','consulted_edition':'Revised reader edition, 23 October 2026','verification_scope':'Accepted frozen annual extract; monthly originals are not re-downloaded during rebuild.','data_role':'WPI annual mean and stock-date proxy context, 1929-1938','access_note':'WPI original base July 1914=100. Full annual means require twelve observations; proxy is following 1 January.'},
 'CPI_LJUNGBERG_WORKBOOK':{'source_id':'CPI_LJUNGBERG_WORKBOOK','title':'European CPI since 1870: research workbook extract','publication_year':2025,'creator':'Jonas Ljungberg; source comment cites Mitchell (2013)','source_type':'research_workbook_cell_extract','source_url':'','local_source_locator':CPI_DOC['workbook'],'consulted_edition':'Frozen research-supplied workbook cell provenance','verification_scope':'Exact cell values and source comment retained; original index base and within-year convention are not established by this extract.','data_role':'Annual Czechoslovak CPI context, available 1923-1938','access_note':CPI_DOC['source_comment_E9'].replace('\n',' ')},
})
for source in source_info.values():source['related_publication_url']=''
source_info['CPI_LJUNGBERG_WORKBOOK']['related_publication_url']='https://doi.org/10.1007/s11698-024-00283-6'
source_info['CPI_LJUNGBERG_WORKBOOK']['access_note']+=' Related article: European consumer price indices since 1870 (Cliometrica, 2025); related_publication_url identifies that article, not a verified workbook download.'
write(META/'source_index.csv',list(source_info.values()))
entry_rows=[]
for r in CAT:
    entry_rows.append({'source_entry_id':r['id'],'source_id':r['source_id'],'publication_year':r['publication_year'],'covered_years':r['coverage'],'original_table_title':r['title'],'printed_pages':r['printed_pages'],'pdf_pages':r['pdf_pages'],'original_source_file':r['source_file'],'accepted_visual_verification':r['visual_verified'].lower(),'selected_record_count':sum(x['entry_id']==r['id'] for x in RAW)})
write(META/'source_entry_index.csv',entry_rows)

populations=[
 {'population_id':POP_ANNUAL,'label':'Changing commercial-bank aggregate in the Czech lands','coverage':'1919-1937','definition':'Active joint-stock banks in Bohemia, Moravia and Silesia in the League source, with changing membership. Headquarters/reporting coverage does not prove domestic-only branch assets.','exclusions_and_limits':'Separate eastern joint-stock institutions, ordinary savings banks, cooperative credit associations and provincial banks are outside this group. Joint-stock savings/cooperative central institutions may belong. No fixed membership inferred from equal counts.'},
 {'population_id':POP_INCOME,'label':'Reported commercial-bank income population','coverage':'1919-1937','definition':'Annual profit-and-loss reporting population. Its published count is 22 in 1936 while the balance-sheet count is 23.','exclusions_and_limits':'Matching published counts elsewhere does not prove identical members. Income/end-assets ratios suppress the known 1936 mismatch.'},
 {'population_id':POP_PANEL,'label':'Fourteen named handbook banks','coverage':'1933-1937','definition':'Retrospective cohort of Czech-lands-headquartered commercial/deposit-credit joint-stock banks with complete tables in the selected 1938 handbook chapters.','exclusions_and_limits':'Handbook availability sample; not a random sample or failure panel. All fourteen map to the 1929 national roster; later League membership remains unmatched. Sporobanka changes mandate in 1937.'},
 {'population_id':POP_NB,'label':'National Bank of Czechoslovakia','coverage':'1929-1937','definition':'Separate central-bank balance-sheet context from the League.','exclusions_and_limits':'Not added to commercial-bank totals; loans to banks cannot be fully reconciled to commercial-bank creditor categories.'},
 {'population_id':POP_NAT,'label':'National twenty-two-bank roster','coverage':'1929','definition':'The twenty-two named joint-stock institutions in national table X5, printed page 259.','exclusions_and_limits':'A dated roster, not proof of later League membership. Footprint shares use numerator and denominator from this same source year.'},
 {'population_id':POP_PRICE,'label':'Czechoslovak price context','coverage':'1919-1938 display grid; actual CPI 1923-1938, WPI extract 1929-1938','definition':'Separate CPI and WPI context, with source-specific bases and timing.','exclusions_and_limits':'Not prices specific to the bank sample. CPI1919-1922 is unavailable; WPI1929/1938 incomplete; no annual-mean infilling.'},
]
write(META/'population_definitions.csv',populations)

# Add canonical derived aggregate levels once; convenience copies of reported
# quantities remain only in the wide view and lineage table.
CORE_DERIVED={'loans_and_bills','identified_sundry_loans','extended_credit','broad_cash','capital_and_reserves','total_deposits'}
long_rows=[cell for cell in CELLS.values() if cell['dataset_id'] in LONG_TABLES or (cell['dataset_id']=='annual_aggregate' and cell['variable_id'] in CORE_DERIVED)]
write(DATA/'observations_long.csv',long_rows)
TABLES['observations_long']=long_rows
write(META/'raw_to_analytic.csv',LINEAGE)

# Every public data column receives a machine-readable definition; monetary
# measures have explicit units and all identifier/provenance fields have roles.
COMMON={
 'year':'Calendar year of the observation; balance-sheet stocks are year-end unless a source-date field says otherwise.',
 'population_id':'Join key to metadata/population_definitions.csv; populations must not be pooled or added without a defined bridge.',
 'bank_id':'Stable ASCII institution identifier retained from the accepted named-bank panel.',
 'bank_name':'UTF-8 canonical bank name; spelling retains historical Czech/German names.',
 'flags':'Semicolon-separated source or comparability exception codes; empty means no listed exception, not an assurance of universal comparability.',
 'source_id':'Source identifier joining metadata/source_index.csv.',
 'source_ids':'Semicolon-separated source identifiers joining metadata/source_index.csv.',
 'source_entry_ids':'Semicolon-separated source-table entries joining metadata/source_entry_index.csv.',
 'source_record_ids':'Semicolon-separated accepted source record or bank-table-cell identifiers; exact mappings are in metadata/raw_to_analytic.csv.',
 'source_pages':'Printed and/or digital source locations; digital handbook page numbers are not original-edition pagination.',
 'source_url':'Recorded public source URL, not a rebuild dependency or newly verified publication link.',
 'source_original_unit':'Units printed in the source; Všeobecná družstevní is in thousands while release money values are millions.',
 'source_edition':'Consulted digital/source edition; does not certify an original annual-report facsimile.',
 'original_annual_report_verified':'False: original bank annual-report facsimiles were not independently checked; the consulted handbook edition was checked.',
 'asset_pdf_page':'Digital handbook page containing the asset table.',
 'liability_pdf_page':'Digital handbook page containing the liability table.',
 'income_pdf_page':'Digital handbook page containing the income table.',
 'asset_component_residual':'Calculated sum of reported asset components minus published total; explicit dashes add no reported amount for this audit only. Not an imputed balance-sheet component.',
 'category_notes':'Bank-specific category qualifications retained from the accepted transcription.',
 'balance_bank_count':'Published balance-sheet reporting count. Equal counts do not prove identical membership.',
 'income_bank_count':'Published profit-and-loss reporting count; 22 in 1936 against 23 for balance sheets.',
 'income_balance_counts_match':'True when published balance-sheet and income counts match. This does not establish identity of individual members.',
 'deposits_comparable':'True when the deposit item excludes separately identified bank creditors under the 1920-1937 definition; false in 1919.',
 'cash_definition':'Source definition of the separate or combined cash categories, retaining the 1931 classification boundary.',
 'deposit_definition':'Source definition of the deposit category, including the 1919 unseparated-bank-creditor exception.',
 'observation_id':'Stable analytical-cell key: dataset_id:entity_id:year:variable_id.',
 'dataset_id':'Identifier of the source analytical table; join to metadata/dataset_index.csv.',
 'entity_id':'Aggregate, bank, event or category identifier. Interpret with dataset_id and population_id.',
 'variable_id':'Variable identifier within dataset_id; join to the variable dictionary.',
 'value':'Numeric value, or empty for unavailable/inapplicable observations. Interpret value_status, observation_type and unit.',
 'unit':'Machine-readable measurement unit. row_unit means read the unit column of that row.',
 'observation_type':'reported or derived. Status additionally distinguishes missingness and the accepted national dash-to-zero convention.',
 'value_status':'Reported, derived, source dash, unavailable, not comparable or another explicit code defined in metadata/value_status_codes.csv.',
 'original_symbol':'Literal source dash when known; empty does not certify that the original source printed a blank.',
 'notes':'Observation-specific interpretation or source qualification.',
 'source_record_id':'Stable identifier from the accepted selected-source ledger.',
 'source_entry_id':'Accepted source-table entry identifier.',
 'publication_year':'Publication year of the referenced source, distinct from observation year.',
 'source_block':'Original balance-sheet, profit-and-loss or components block.',
 'source_variable_id':'Original accepted transcription variable identifier before aliases and analytic renaming.',
 'original_variable_label':'Original transcribed variable label; may be Czech or English and is retained verbatim.',
 'original_unit':'Verbatim source/transcription unit before release normalization.',
 'original_note':'Verbatim accepted source note, including Czech notes where present.',
 'printed_pages':'Page numbers printed in the historical publication.',
 'pdf_pages':'One-based page positions in the consulted PDF file.',
 'original_frequency':'Verbatim frequency convention in the accepted source ledger.',
 'wpi_proxy_source_date':'Date of the following 1 January observation used as a year-end proxy; not a 31 December quotation.',
 'cpi_source_cell':'Cell address in the frozen CPI workbook provenance.',
 'national_source_id':'Original national source identifier (National1932 corresponds to source_index NATIONAL_1932).',
 'national_printed_page':'Historical printed page of the named national roster.',
 'national_pdf_page_part4':'One-based PDF page in the supplied part-four national file.',
 'national_table':'Historical national table and legal-form grouping.',
 'national_year':'Year of the national roster, always 1929.',
 'national_row':'Original numbered institution row in national table X5.',
 'national_bank_id':'Stable short identifier for a national-roster institution; distinct from the panel bank_id.',
 'national_bank_name':'Name printed/transcribed in the national 1929 roster.',
 'national_headquarters':'Headquarters location in the national roster; not the location of every asset or branch.',
 'national_legal_classification':'Joint-stock classification in national table X5.',
 'institution_type_note':'Verified functional/type qualification; no further subtype is inferred when unestablished.',
 'included_in_1933_1937_panel':'Whether this 1929 institution has the explicit named counterpart in the fourteen-bank panel.',
 'panel_bank_id':'Matched panel bank identifier; empty when no identity link is established.',
 'panel_bank_name':'Matched canonical panel name; empty for unmatched national institutions.',
 'match_class':'Exact canonical name, geographic qualifier, documented rename or unmatched separate institution.',
 'identity_basis':'Evidence supporting an institution identity match, without assuming an unchanged business perimeter.',
 'selection_status':'Availability/selection reason; missing handbook coverage does not establish failure or absorption.',
 'kaspar_identity_pdf_pages':'Digital handbook pages supporting identities or, for unmatched banks, contextual mentions.',
 'kaspar_asset_pdf_page':'Digital handbook page of matched bank asset accounts.',
 'kaspar_liability_pdf_page':'Digital handbook page of matched bank liability accounts.',
 'kaspar_income_pdf_page':'Digital handbook page of matched bank income accounts.',
 'history_or_scope_note':'Dated name, merger, mandate or affiliate qualification.',
 'later_outcome_status':'What the consulted sources establish about later institutional status; unestablished outcomes remain explicit.',
 'related_panel_bank_id_not_identity':'Related affiliate/supporting bank; expressly not an institution identity or merger mapping.',
 'lon_1929_link':'Scope and rounded-control support for the 1929 League population link.',
 'lon_1933_1937_membership':'Later individual League membership remains unestablished; equal counts do not prove membership.',
 'lon_named_narrative_reference':'League narrative naming the institution, where available; not an annual roster.',
 'national_amounts_unit':'Original national monetary unit; numeric crosswalk columns remain thousand Kč.',
 'source_edition_note':'Edition/provenance qualification across the national scan and handbook retyping.',
 'zero_value_convention':'Accepted national dash-to-zero accounting convention; these zeros are distinct from printed numerical zeros.',
 'measure':'Coverage category identifier. Read the unit column: monetary footprint totals are in millions of Kč, while the institution crosswalk retains its original thousand-Kč unit.',
 'label':'Human-readable coverage category.',
 'interpretation':'Limit on what the observation, event or footprint can establish.',
 'event_id':'Stable dated accounting-event identifier.',
 'event_date':'Exact date when documented; empty when only the event year is established.',
 'event_type':'Classification of the accounting transaction or opening-balance adjustment.',
 'amount_status':'Distinguishes an explicitly reported transfer/utilization from a calculated opening adjustment.',
 'event_description':'Description of the dated transaction, preserving source category boundaries.',
 'source_pdf_pages':'Digital handbook source pages, separated by semicolons.',
}
DICT=[]
for table,rows in TABLES.items():
    for col in rows[0]:
        cfg=COLUMN_SPEC.get((table,col),{})
        description=cfg.get('description') or COMMON.get(col)
        if description is None: raise ValueError('Undocumented public column '+table+'.'+col)
        values=[r.get(col) for r in rows if r.get(col) not in (None,'')]
        if cfg: dtype=cfg.get('data_type','number')
        elif values and all(isinstance(v,bool) or str(v) in ('true','false') for v in values):dtype='boolean'
        elif col in {'year','publication_year','national_year','national_row','balance_bank_count','income_bank_count','asset_pdf_page','liability_pdf_page','income_pdf_page','national_printed_page','national_pdf_page_part4','kaspar_asset_pdf_page','kaspar_liability_pdf_page','kaspar_income_pdf_page'}:dtype='integer'
        elif col in {'asset_component_residual','value'}:dtype='number'
        else:dtype='string'
        unit=cfg.get('unit','')
        if col=='asset_component_residual':unit=MONEY
        DICT.append({'dataset_id':table,'column_name':col,'label':cfg.get('original_label') or col.replace('_',' ').capitalize(),'description':description,'data_type':dtype,'unit':unit,'role':cfg.get('role','measure' if dtype=='number' else 'provenance_or_identifier'),'formula':cfg.get('formula',''),'original_source_label':cfg.get('original_label',''),'input_source_column':cfg.get('source_column',''),'missing_value_encoding':'empty CSV field; never implicit zero','status_detail_location':'data/observations_long.csv; metadata/raw_to_analytic.csv'})
write(META/'variable_dictionary.csv',DICT)
jsonwrite('variable_dictionary.json',DICT)

status_def={
 'reported':'A numerical value retained from the accepted source transcription.',
 'reported_zero':'An explicitly numerical source zero, distinct from a dash or missing observation.',
 'derived':'Calculated or harmonized value with a stated formula and source dependencies.',
 'derived_zero':'A zero produced by a stated calculation; not represented as a printed source zero.',
 'missing_not_reported':'No numerical value in the selected accepted source/extract. No imputation.',
 'not_separately_reported':'The bank source table does not contain a separate line for this component.',
 'source_dash':'The source cell contains a dash; retained as missing rather than converted to zero.',
 'not_comparable':'Value intentionally withheld from a comparable measure/ratio because of a known category or population-count mismatch.',
 'missing_prerequisite':'A formula lacks at least one required input or prior/base observation.',
 'not_applicable':'This event-specific field does not apply to the transaction described.',
 'source_dash_accounted_as_zero':'The frozen national-roster transcription encodes a printed dash as zero under its validated column-sum convention. This is not a printed numerical zero or new imputation.',
}
write(META/'value_status_codes.csv',[{'value_status':k,'definition':v} for k,v in status_def.items()])

flag_def={
 'deposits_include_unseparated_bank_creditors':'In 1919 the published deposit total includes bank creditors that cannot be separated. The comparable public deposit series and dependent ratios are blank.',
 'income_population_22_balance_population_23':'For 1936 the published income count is 22 and the balance-sheet count is 23. Income/end-assets ratios are withheld; the published levels remain available.',
 'asset_components_below_reported_total_20_million':'Moravská 1933 reported asset components sum to 1955.2 million Kč against the published 1975.2 total. The discrepancy is retained without correction.',
 'savings_bank_central_institution':'Sporobanka is a joint-stock central institution serving savings banks; functional differences remain visible within the panel.',
 'cash_includes_treasury_bills':'Sporobanka source hotovosti include Treasury bills in 1935–1937, so this line is not a narrow reserve-money measure.',
 'savings_bank_mandate_expansion':'Sporobanka received an expanded savings-bank central-institution mandate in 1937; the business perimeter need not be constant.',
 'source_deposits_include_mortgage_borrowing':'Legiobanka source vklady include mortgage borrowing; the line is not harmonized to the League deposit category.',
 'securities_include_participations':'Všeobecná družstevní reports participations within securities, without a separate participation line.',
 'separate_central_bank_population':'The National Bank is a separate institution. These accounts must not be added to commercial-bank totals without consolidation.',
 'source_dash_zero_convention':'The accepted 1929 national-roster transcription uses zero for printed dashes under reconciled column totals. These are not printed numerical zeros.',
 'wpi_outside_frozen_extract':'The frozen WPI extract has no observation for this calendar year. No value is interpolated.',
 'wpi_incomplete_calendar_year':'Fewer than twelve monthly WPI observations are available. The full-calendar-year mean is therefore blank.',
 'cpi_not_available':'No numerical CPI value is available for this year in the frozen workbook extract.',
}
write(META/'flag_definitions.csv',[{'flag':k,'definition':v} for k,v in flag_def.items()])

dataset_desc={
 'annual_aggregate':'Compact annual commercial-bank view: selected reported categories and explicitly derived level measures.',
 'annual_balance_sheet':'Full accepted annual balance-sheet categories, preserving original reported deposits and separate missing components.',
 'annual_income':'Annual income, expenses, write-offs and distribution accounts; separate reporting count.',
 'annual_components':'Detailed annual source components, including cash, special loans, reserve categories and income components.',
 'annual_ratios':'Derived annual shares, income intensities, indexes and growth rates with stated eligibility rules.',
 'bank_panel':'Seventy annual observations for fourteen named banks, with source-specific account categories.',
 'bank_ratios':'Derived bank-year shares and within-bank 1933-based indexes; no estimation or causal model.',
 'central_bank_context':'Separate National Bank context, never pooled into commercial-bank totals.',
 'price_context':'Separate CPI/WPI context with honest coverage and timing; no missing-year interpolation.',
 'institution_crosswalk_1929':'Full national twenty-two-bank roster, fourteen named matches and eight explicit unmatched institutions.',
 'coverage_1929':'Source-internal 1929 footprint of the later fourteen-bank cohort; not later asset coverage.',
 'reserve_events':'Five dated accounting events, distinguishing transfers, separate funds and opening adjustments.',
 'source_observations':'Original selected-source ledger in normalized English column names; may repeat facts displayed in analytical tables.',
 'observations_long':'Canonical analytical cells with populations, units, missingness and source references. Convenience copies are excluded.',
}
INDEX=[]
for table,rows in TABLES.items():
    key='year'
    if table.startswith('bank_'):key='bank_id;year'
    elif table=='institution_crosswalk_1929':key='national_bank_id'
    elif table=='coverage_1929':key='measure'
    elif table=='reserve_events':key='event_id'
    elif table=='source_observations':key='source_record_id'
    elif table=='observations_long':key='observation_id'
    INDEX.append({'dataset_id':table,'path':'data/'+table+'.csv','description':dataset_desc[table],'rows':len(rows),'columns':len(rows[0]),'primary_key':key,'encoding':'UTF-8','missing_value':'empty field','canonical_long_inclusion':'yes' if table in LONG_TABLES else 'derived levels only' if table=='annual_aggregate' else 'not applicable / source ledger' if table=='source_observations' else 'canonical long table'})
write(META/'dataset_index.csv',INDEX)

# Focused audit: identities, explicit exceptions, source/value preservation,
# provenance joins and nonimputation. Small printed rounding residuals are retained.
failures=[]
def check(condition,message):
    if not condition:failures.append(message)
for item in INDEX:
    rows=TABLES[item['dataset_id']];keys=item['primary_key'].split(';')
    check(len({tuple(str(r[k]) for k in keys) for r in rows})==len(rows),'Duplicate keys: '+item['dataset_id'])
check(len(CORE)==19 and len(PANEL)==70,'Core dimensions')
check(len({x['bank_id'] for x in PANEL})==14,'Panel bank count')
check(all(sum(r['bank_id']==b for r in PANEL)==5 for b in NAMES),'Unbalanced panel')
check(corey[1919]['reported_deposits_total']=='10740' and corey[1919]['total_deposits']=='','1919 deposit preservation and exclusion')
check(corey[1936]['balance_bank_count']=='23' and corey[1936]['income_bank_count']=='22','1936 published count mismatch')
check(all(next(r for r in AR if r['year']==1936)[c]=='' for c in ['net_interest_assets_pct','commissions_assets_pct','net_profit_assets_pct']),'1936 income/assets suppression')
check(next(r for r in PANEL if r['bank_id']=='moravska' and r['year']==1933)['total_assets']=='1975.2','Moravská published total retained')
check(next(r for r in PANEL if r['bank_id']=='moravska' and r['year']==1933)['asset_component_residual']=='-20.0','Moravská discrepancy retained')
check(all(x['value_status'] in status_def for x in long_rows),'Unknown status code')
check(all(not x['value'] for x in long_rows if x['value_status'] in {'source_dash','not_comparable','not_separately_reported','missing_not_reported','missing_prerequisite','not_applicable'}),'Missing statuses contain numerical values')
check(all(re.match(r'^[a-z][a-z0-9_]*$',c) for rows in TABLES.values() for c in rows[0]),'Non-English-snake-case column')
check(len(DICT)==sum(len(rows[0]) for rows in TABLES.values()),'Incomplete column dictionary')
check(all(s in source_info for c in long_rows for s in c['source_ids'].split(';') if s),'Unknown source reference')
check(all(f in flag_def for c in long_rows for f in c['flags'].split(';') if f),'Unknown exception flag')
check(all(x['observation_type']=='derived' for x in long_rows if x['value_status'] in {'derived','derived_zero'}),'Derived status/type mismatch')
check(all(x['observation_type']=='reported' for x in long_rows if x['value_status'] in {'reported','reported_zero','source_dash_accounted_as_zero'}),'Reported status/type mismatch')
check(all('cpi:'+CPI[1929]['cell'] in x['source_record_ids'].split(';') for x in long_rows if x['dataset_id']=='price_context' and x['variable_id']=='cpi_1929_100'),'CPI rebasing lacks base-year provenance')
check(all(next(r for r in PRICE if r['year']==y)['cpi_source_index']=='' for y in range(1919,1923)),'CPI early coverage')
check(all(next(r for r in PRICE if r['year']==y)['wpi_annual_mean']=='' for y in (1929,1938)),'Partial-year WPI was averaged')
check(sum(r['included_in_1933_1937_panel'] for r in CROSS)==14,'Crosswalk matched count')
expected={'paid_capital_thousand_kc':1844600,'loss_cover_reserves_thousand_kc':1382203,'book_and_cash_certificate_deposits_thousand_kc':8927082,'creditors_thousand_kc':17491957,'own_bonds_thousand_kc':268236}
check(all(sum(int(r[c]) for r in CROSS)==v for c,v in expected.items()),'National roster controls')
for row in CORE:
    original=bybs[row['year']]
    for new,old in [('loans_and_bills','broad_credit'),('capital_and_reserves','capital_and_reserves'),('broad_cash','broad_cash'),('identified_sundry_loans','identified_sundry_loans'),('extended_credit','extended_credit')]:
        check(number(row[new])==number(original[old]),f'Accepted level mismatch {row["year"]}:{new}')

VALIDATION={'version':VERSION,'release_date':DATE,'status':'pass' if not failures else 'fail','failures':failures,'checks':{'frozen_input_checksums':len(INPUT_MANIFEST),'all_public_columns_documented':len(DICT),'all_exception_flags_documented':len(flag_def),'annual_years':19,'bank_years':70,'banks':14,'crosswalk_institutions':22,'matches':14,'events':5,'no_interpolation':True,'no_new_dash_to_zero_conversion':True,'national_preexisting_dash_zero_convention_explicit':True,'1919_comparable_deposits_withheld':True,'1936_income_ratios_withheld':True,'moravska_1933_discrepancy_preserved':True,'original_annual_report_verification_not_claimed':True},'known_source_exceptions':['Moravská 1933 assets: components 1955.2 versus reported total 1975.2 million Kč; no correction.','League 1936 income reports 22 banks versus 23 for balance sheets.','National 1929 accepted source dashes were encoded as zero under independently reconciled column totals; statuses preserve the distinction.','Full-year WPI means unavailable for 1929 and 1938; CPI unavailable before 1923 in the frozen extract.'],'population_warning':'Matching counts or name matches do not establish constant reporting membership; no cross-population aggregation is performed.'}
jsonwrite('validation.json',VALIDATION)
counts=Counter(x['value_status'] for x in long_rows)
reported_records={x['source_record_id'] for x in SOURCE_OBS if x['value']!=''}
COUNTS={'version':VERSION,'release_date':DATE,'annual_years':19,'annual_start_year':1919,'annual_end_year':1937,'bank_years':70,'banks':14,'panel_start_year':1933,'panel_end_year':1937,'central_bank_years':9,'national_roster_institutions':22,'matched_roster_institutions':14,'reserve_events':5,'price_grid_years':20,'cpi_available_years':sum(r['cpi_source_index']!='' for r in PRICE),'wpi_full_annual_mean_years':sum(r['wpi_annual_mean']!='' for r in PRICE),'public_csv_tables':len(TABLES),'canonical_analytic_cells_including_missing':len(long_rows),'canonical_value_status_counts':dict(counts),'canonical_numeric_cells':sum(x['value']!='' for x in long_rows),'source_ledger_records':len(SOURCE_OBS),'source_ledger_numeric_records':len(reported_records),'dictionary_columns':len(DICT),'source_publications_or_extracts':len(source_info),'counts_note':'Canonical cells exclude repeated reported facts in annual_aggregate and exclude the separate source ledger. Detail categories, accounting totals, event views and ratios are still related; these counts are not independent measurements or a statistical sample size. Headline sample sizes are 19 annual years and 70 bank-years.'}
jsonwrite('release_counts.json',COUNTS)
jsonwrite('input_manifest.json',INPUT_MANIFEST)
print(json.dumps({'status':VALIDATION['status'],'tables':len(TABLES),'annual_years':19,'bank_years':70,'long_rows':len(long_rows),'dictionary_columns':len(DICT),'failures':failures},indent=2))
if failures:raise SystemExit(1)
