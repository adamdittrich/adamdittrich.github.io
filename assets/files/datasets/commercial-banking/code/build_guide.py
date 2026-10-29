#!/usr/bin/env python3
"""Build four public research charts and a four-page dataset guide.

Requires pandas, numpy, matplotlib and reportlab. Reads only release CSVs.
Run from any directory: python /path/to/release/code/build_guide.py
"""
from pathlib import Path
from io import BytesIO
import os
import tempfile
import numpy as np
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'czechoslovak_banking_plot_cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, Image, PageBreak, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'figures'
DOC = ROOT / 'docs'
INK = '#162b36'
BURGUNDY = '#7a2e34'
TEAL = '#287c81'
GOLD = '#a77530'
GREY = '#67767e'
PAPER = '#f4f0e7'
LINE = '#d6d0c6'


def save_figure(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.subplots_adjust(bottom=.23)
    for extension in ['pdf', 'png']:
        memory = BytesIO()
        fig.savefig(memory, format=extension, dpi=190,
                    facecolor='white', bbox_inches='tight')
        data = memory.getvalue()
        destination = FIG / f'{name}.{extension}'
        destination.write_bytes(data)
        if destination.read_bytes() != data:
            raise IOError(f'Incomplete write: {destination}')
    plt.close(fig)


def style_axis(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.spines[['left', 'bottom']].set_color(LINE)
    ax.tick_params(colors=INK, length=3)
    ax.grid(axis='y', color=LINE, linewidth=.65, alpha=.65)
    ax.set_axisbelow(True)


def build_charts():
    annual = pd.read_csv(ROOT / 'data/annual_aggregate.csv')
    ratios = pd.read_csv(ROOT / 'data/annual_ratios.csv')
    banks = pd.read_csv(ROOT / 'data/bank_panel.csv')
    br = pd.read_csv(ROOT / 'data/bank_ratios.csv')
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':10.5,
                         'axes.labelcolor':INK, 'text.color':INK,
                         'axes.titleweight':'bold', 'axes.titlesize':13,
                         'axes.unicode_minus':False})
    fig, ax = plt.subplots(figsize=(9.4,4.8))
    for variable, label, colour, linestyle in [
        ('assets_index_1930_100','Assets',INK,'-'),
        ('loans_bills_index_1930_100','Loans and bills',TEAL,'--'),
        ('deposits_index_1930_100','Comparable deposits',GREY,'-.'),
        ('capital_reserves_index_1930_100','Published capital and reserves',BURGUNDY,':')]:
        ax.plot(ratios.year, ratios[variable], label=label, color=colour,
                linestyle=linestyle, linewidth=2.3)
    ax.axvspan(1931,1933,color=PAPER,zorder=0)
    ax.axhline(100,color=LINE,lw=.9,zorder=0)
    ax.set(xlabel='Year', ylabel='Index, 1930 = 100', xlim=(1919,1937))
    ax.set_title('Commercial-bank balance sheets, 1919-1937',loc='left',pad=16)
    ax.set_xticks([1919,1922,1925,1928,1931,1934,1937])
    ax.legend(frameon=False,loc='lower right',fontsize=9.5)
    style_axis(ax)
    fig.text(.11,.025,'Changing aggregate of joint-stock banks in the Czech lands. Deposits begin in 1920.\nSource: League of Nations banking volumes; frozen observations in this release.',fontsize=8.8,color=GREY)
    save_figure(fig,'commercial_bank_stocks_1919_1937')

    first=br[br.year.eq(1933)].set_index('bank_id')
    last=br[br.year.eq(1937)].set_index('bank_id')
    changes=(last.capital_assets_pct-first.capital_assets_pct).sort_values()
    short={'agrarni':'Agrární','anglo':'Anglo-československá','ceska':'Česká banka',
           'escomp':'Česká eskomptní','union':'Česká banka Union','prumyslova':'Česká průmyslová',
           'deutagr':'Deutsche Agrar','lander':'Länderbanka',
           'legio':'Legiobanka','moravska':'Moravská','plzenska':'Plzeňská',
           'sporobanka':'Savings-bank central','vseobdruz':'Všeobecná družstevní','zivno':'Živnostenská'}
    labels=[short.get(k,first.loc[k,'bank_name']) for k in changes.index]
    fig,ax=plt.subplots(figsize=(9.4,6.1))
    ax.barh(labels,changes,color=[BURGUNDY if v<0 else TEAL for v in changes])
    ax.axvline(0,color=INK,lw=.8);ax.invert_yaxis()
    ax.set_xlabel('Change in published capital / assets, percentage points')
    ax.set_title('Capital ratios within fourteen banks, 1933-1937',loc='left',pad=14)
    ax.grid(axis='x',color=LINE,lw=.7);ax.set_axisbelow(True)
    ax.spines[['top','right','left']].set_visible(False)
    ax.spines['bottom'].set_color(LINE)
    fig.text(.13,.025,'Same named institutions at both dates. Published capital is paid capital plus published reserves.\nSource: Kašpar bank handbook, consulted digital retyping; bank_ratios.csv.',fontsize=8.8,color=GREY)
    save_figure(fig,'bank_capital_changes_1933_1937')

    a=annual.set_index('year')
    cols=['broad_cash','bills_discounted','loans_advances','securities','participations','premises','sundry_assets']
    vals=[float(a.loc[1937,c]-a.loc[1933,c]) for c in cols]
    labels=['Cash and cash-like','Discounted bills','Loans and advances','Securities','Participations','Premises','Sundry assets']
    fig,ax=plt.subplots(figsize=(9.4,4.7))
    bars=ax.barh(labels,vals,color=[TEAL if v>=0 else BURGUNDY for v in vals])
    ax.invert_yaxis();ax.axvline(0,color=INK,lw=.8)
    for bar,value in zip(bars,vals):
        ax.text(max(value,0)+14,bar.get_y()+bar.get_height()/2,f'{value:+,.0f}',va='center',fontsize=10)
    ax.set_xlim(min(vals)-40,max(vals)+180)
    ax.set(xlabel='Change, million nominal Kč')
    ax.set_title('What grew during the recovery, 1933-1937?',loc='left',pad=15)
    ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color(LINE)
    ax.grid(axis='x',color=LINE,lw=.7);ax.set_axisbelow(True)
    fig.text(.13,.025,'Changing League aggregate. Components sum to the 3,629 million Kč increase in gross assets.\nSource: League of Nations banking volumes; annual_aggregate.csv.',fontsize=8.8,color=GREY)
    save_figure(fig,'banking_recovery_composition_1933_1937')

    sums=banks.groupby('year')[['total_assets','net_interest','commissions']].sum()
    indexed=sums.div(sums.loc[1933]).mul(100)
    fig,ax=plt.subplots(figsize=(9.4,4.8))
    for col,label,colour,linestyle in [('total_assets','Assets',INK,'-'),('net_interest','Net interest',BURGUNDY,':'),('commissions','Commissions',TEAL,'--')]:
        ax.plot(indexed.index,indexed[col],label=label,color=colour,linestyle=linestyle,lw=2.5,marker='o',ms=4)
    ax.set(xlabel='Year',ylabel='Index, 1933 = 100');ax.set_xticks(indexed.index)
    ax.set_title('Assets and earnings in the fixed bank panel',loc='left',pad=16)
    ax.axhline(100,color=LINE,lw=.8);style_axis(ax);ax.legend(frameon=False,loc='upper left')
    fig.text(.11,.025,'Fourteen banks in every year; aggregate nominal amounts indexed separately.\nSource: Kašpar bank handbook, consulted digital retyping; bank_panel.csv.',fontsize=8.8,color=GREY)
    save_figure(fig,'bank_income_1933_1937')


def build_pdf():
    from matplotlib.font_manager import findfont, FontProperties
    for name,family,weight in [('Body','DejaVu Sans','normal'),('BodyBold','DejaVu Sans','bold'),
                               ('Serif','DejaVu Serif','normal'),('SerifBold','DejaVu Serif','bold')]:
        pdfmetrics.registerFont(TTFont(name,findfont(FontProperties(family=family,weight=weight))))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
    styles={
        'title':ParagraphStyle('title',fontName='SerifBold',fontSize=29,leading=34,textColor=colors.HexColor(INK),spaceAfter=9),
        'subtitle':ParagraphStyle('subtitle',fontName='Serif',fontSize=16,leading=21,textColor=colors.HexColor(BURGUNDY),spaceAfter=14),
        'h1':ParagraphStyle('h1',fontName='SerifBold',fontSize=21,leading=27,textColor=colors.HexColor(INK),spaceAfter=13),
        'h2':ParagraphStyle('h2',fontName='BodyBold',fontSize=11,leading=15,textColor=colors.HexColor(BURGUNDY),spaceBefore=13,spaceAfter=5),
        'body':ParagraphStyle('body',fontName='Body',fontSize=9.6,leading=14,textColor=colors.HexColor(INK),spaceAfter=8),
        'small':ParagraphStyle('small',fontName='Body',fontSize=8.1,leading=11.5,textColor=colors.HexColor(GREY),spaceAfter=6),
        'cell':ParagraphStyle('cell',fontName='Body',fontSize=8.1,leading=11.5,textColor=colors.HexColor(INK)),
        'headcell':ParagraphStyle('headcell',fontName='BodyBold',fontSize=8.1,leading=11.5,textColor=colors.white),
        'mono':ParagraphStyle('mono',fontName='Courier',fontSize=8,leading=12,textColor=colors.HexColor(INK),spaceAfter=8),
    }
    def p(text,style='body'): return Paragraph(text,styles[style])
    def table(rows,widths):
        cells=[[p(str(v),'headcell' if i==0 else 'cell') for v in row] for i,row in enumerate(rows)]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor(INK)),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor(PAPER)]),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
            ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),
            ('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,-1),(-1,-1),.5,colors.HexColor(LINE))]))
        return t
    def pic(name,width=487):
        from PIL import Image as PILImage
        path=FIG/(name+'.png')
        with PILImage.open(path) as im: w,h=im.size
        return Image(str(path),width=width,height=width*h/w)
    def footer(c,doc):
        w,h=A4;c.saveState()
        c.setFillColor(colors.HexColor(BURGUNDY));c.rect(0,h-9,w,9,fill=1,stroke=0)
        c.setStrokeColor(colors.HexColor(LINE));c.line(45,38,w-45,38)
        c.setFont('Body',7.5);c.setFillColor(colors.HexColor(GREY))
        c.drawString(45,25,'Czechoslovak Commercial Banking | Dataset version 0.1.0')
        c.drawRightString(w-45,25,str(doc.page));c.restoreState()
    story=[]
    story += [p('Czechoslovak<br/>Commercial Banking','title'),
              p('1919-1937 | Joint-stock banks in the Czech lands','subtitle'),
              p('A research dataset by Adam Dittrich<br/>Version 0.1.0 | Released 29 October 2026','small'),
              p('Annual accounts, named banks and the sources behind the numbers. This release combines downloadable research tables with an Excel edition and an interactive dataset page.'),
              table([['Annual commercial accounts','Named-bank panel','National roster'],
                     ['19 years<br/>1919-1937','14 banks, 70 bank-years<br/>1933-1937','22 institutions<br/>1929 crosswalk']], [163,163,161]),
              Spacer(1,12),pic('commercial_bank_stocks_1919_1937'),
              p('The annual series follows a changing population of banks. The named-bank panel follows the same fourteen institutions. Their observations retain distinct definitions and source identifiers.','small'),
              p('Explore first, then download','h2'),
              p('Open <b>index.html</b> for the standalone dataset page or the <b>Excel workbook</b> for a tabular view. The complete archive includes the CSV data, source dictionary, frozen inputs and reconstruction code.')]
    story.append(PageBreak())
    story += [p('What the release contains','h1'),
              p('The core tables cover commercial banking. National Bank and price observations are separate context, with their own coverage.'),
              table([['Files in data/','Coverage and content'],
                     ['annual_aggregate.csv','19 annual rows. Principal assets, funding, income, reporting counts and comparability flags.'],
                     ['annual_balance_sheet.csv<br/>annual_income.csv<br/>annual_components.csv','Full source-oriented annual detail: assets, liabilities, expenditure, write-offs, profit appropriation, cash and lending components.'],
                     ['annual_ratios.csv','Capital, lending and funding shares; income intensities; annual growth; indices with 1930 = 100.'],
                     ['bank_panel.csv<br/>bank_ratios.csv','70 observations with stable bank identifiers, original category notes, source pages, ratios and indices with 1933 = 100.'],
                     ['institution_crosswalk_1929.csv<br/>coverage_1929.csv','22 national institutions, fourteen later-panel matches, omitted cases and dated coverage measures.'],
                     ['central_bank_context.csv<br/>price_context.csv','Nine National Bank years, 1929-1937. CPI values from 1923 and available WPI observations with explicit timing and gaps.'],
                     ['reserve_events.csv','Dated reserve and stabilisation transactions, with their accounting meanings.'],
                     ['observations_long.csv<br/>source_observations.csv','Tidy analytical records and the separate selected-source ledger, with original publication identifiers, labels, symbols and page references.']], [213,274]),
              p('Two ways to work','h2'),
              p('Use a wide table for a quick time-series or panel analysis. Use the tidy table when selecting variables programmatically or joining observations to their source metadata. The wide and long formats repeat the same underlying values; their row counts should not be added.'),
              p('Definitions travel with the data','h2'),
              p('The metadata folder contains a variable dictionary, population definitions, source index, raw-to-analytic mapping, release counts and generated checks. The inputs folder preserves the transcribed observations used to build the release.')]
    story.append(PageBreak())
    story += [p('Reading the accounts correctly','h1'),
              table([['Measure or issue','Interpretation'],
                     ['Geography and banks','The aggregate covers active joint-stock banks in Bohemia, Moravia and Silesia. It is not a census of all Czechoslovak financial institutions.'],
                     ['Units and dates','Core accounts are nominal millions of Kč. National-roster columns explicitly retain thousands. Balance sheets are year-end stocks; income accounts are annual flows.'],
                     ['Published capital','Paid capital plus the explicitly published reserve line. Hidden reserves, pension and earmarked funds are not automatically included.'],
                     ['Lending-related claims','Loans and bills can include bank and correspondent claims. They do not identify domestic nonfinancial customer credit alone.'],
                     ['Bank creditors and deposits','Bank-panel general creditors are not interbank liabilities alone. Source deposit categories differ across institutions.'],
                     ['Income ratios','Annual income divided by end-year assets measures income intensity, rather than a conventional net interest margin.'],
                     ['Missing observations','Blanks remain missing. Source zero, derived zero and accepted national-roster treatment of a dash are distinguished in the metadata.']], [137,350]),
              p('Two visible comparability breaks','h2'),
              p('<b>1919:</b> the reported creditor/deposit category includes bank creditors that cannot be separated. The comparable deposits field is blank, while the original reported total is retained.'),
              p('<b>1936:</b> the aggregate income account covers 22 banks against 23 balance sheets. Income-to-assets ratios are withheld for this year. Matching counts elsewhere do not establish identical membership.'),
              p('Source exceptions remain visible','h2'),
              p('Moravská banka has a 20 million Kč asset-component discrepancy in 1933. The printed total and the discrepancy are both preserved. The handbook is identified as the consulted digital retyping. The 1929 crosswalk measures a dated footprint, not later League asset coverage.')]
    story.append(PageBreak())
    story += [p('Reuse, reproduce and share','h1'),
              p('Examples of questions the data can support','h2'),
              p('How did banking scale and composition change across the 1920s and 1930s? Which banks expanded during recovery? How much did capital ratios change within institutions? Did lending, deposits and earnings return at the same pace? Which results depend on a published accounting category or a price concept?'),
              p('The observations establish balance-sheet and income patterns. Identifying credit supply, borrower demand or policy effects requires an additional research design.'),
              p('A short Python example','h2'),
              p("import pandas as pd<br/>r = pd.read_csv('data/annual_ratios.csv')<br/>r[['year', 'capital_assets_pct',<br/>&nbsp;&nbsp;&nbsp;'loans_bills_assets_pct']].set_index('year').plot()",'mono'),
              p('Rebuild the data from the frozen inputs','h2'),
              p('python code/build_dataset.py','mono'),
              p('The data transformation is offline and independent of the workbook renderer. The guide and figure builder uses pandas, matplotlib and reportlab. Read README.txt for file conventions and examples in Python, R and Stata.'),
              p('Sources','h2'),
              p('League of Nations commercial-banking volumes (1931, 1934, 1935, 1938 and 1939); the national statistical handbook (1932, 1929 bank roster); Kašpar\'s contemporary bank handbook (1938, consulted digital retyping); National Bank reports and the retained CPI research supplement. Exact publications, pages, original units and source identifiers are in metadata/source_index.csv and the observation records.'),
              p('Citation','h2'),
              p('Dittrich, Adam (2026). <i>Czechoslovak Commercial Banking, 1919-1937: Joint-stock banks in the Czech lands.</i> Version 0.1.0. Research dataset, released 29 October 2026.'),
              p('Public release and reuse','h2'),
              p('The dataset page is available at <link href="https://adamdittrich.github.io/czechoslovak-commercial-banking.html">adamdittrich.github.io/czechoslovak-commercial-banking.html</link>. Cite the version and retain the underlying source references. No additional reuse licence or DOI is assigned. Source publications and software retain their own terms.')]
    DOC.mkdir(exist_ok=True)
    destination=DOC/'Banking_Dataset_Guide.pdf'
    memory=BytesIO()
    doc=SimpleDocTemplate(memory,pagesize=A4,leftMargin=54,rightMargin=54,topMargin=45,bottomMargin=49,
                          title='Czechoslovak Commercial Banking, 1919-1937: Dataset guide',author='Adam Dittrich')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    destination.write_bytes(memory.getvalue())
    print(destination)


if __name__=='__main__':
    build_charts()
    build_pdf()
