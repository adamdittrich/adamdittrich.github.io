#!/usr/bin/env python3
"""Publication-quality overview from the actual integrated district attributes."""
from pathlib import Path
import geopandas as gpd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs';FIG=OUT/'figures'

def main():
 FIG.mkdir(exist_ok=True)
 g=gpd.read_file(OUT/'historical_gis_czech_lands_v06.gpkg',layer='judicial_1930').to_crs(3035)
 fig,axes=plt.subplots(2,2,figsize=(15,11.6),layout=None)
 fig.patch.set_facecolor('#f7f8fa')
 fig.suptitle('Nové vrstvy historického GIS českých zemí',x=.06,y=.975,ha='left',fontsize=23,fontweight='bold',color='#17324d')
 fig.text(.06,.935,'330 soudních okresů v hranicích roku 1930 · skutečně načtené zdroje · vydání 0.6',fontsize=12,color='#435a70')
 specs=[
  ('rail_operating_density_km_per_100km2_1930',1,'Železnice v roce 1930','km provozované tratě / 100 km²','YlOrRd',0,None),
  ('landuse_forest_1845_area_allocated_share',100,'Lesy: historický řez 1845','plošně přidělený podíl (%)','Greens',0,100),
  ('soil_clay_pct_0_30cm',1,'Půda: jílová složka 0–30 cm','% v jemnozemi · moderní model','YlOrBr',0,None),
  ('border_dist_centroid_km_1930',1,'Vzdálenost od hranice ČSR v roce 1930','km od geometrického centroidu','Blues',0,None),
 ]
 sem=g[g.NAZEV.eq('Semily')]
 for ax,(field,mult,title,label,cmap,vmin,vmax) in zip(axes.ravel(),specs):
  vals=g[field]*mult;vmax=float(vals.max()) if vmax is None else vmax
  ax.set_facecolor('#f7f8fa')
  g.assign(_value=vals).plot(column='_value',ax=ax,cmap=cmap,vmin=vmin,vmax=vmax,edgecolor='#ffffff',linewidth=.22,
                            missing_kwds={'color':'#b5b9bf','edgecolor':'white'})
  sem.boundary.plot(ax=ax,color='#b71c42',linewidth=1.45)
  # Dense GIS polygons are rasterized only inside the PDF preview; labels and
  # legends remain vector text. The GeoPackage retains the full geometries.
  for collection in ax.collections:collection.set_rasterized(True)
  ax.set_title(title,loc='left',fontsize=15,fontweight='bold',color='#17324d',pad=7)
  ax.set_axis_off()
  sm=ScalarMappable(norm=Normalize(vmin=vmin,vmax=vmax),cmap=cmap)
  cb=fig.colorbar(sm,ax=ax,orientation='horizontal',shrink=.82,pad=.015,aspect=35,fraction=.04)
  cb.set_label(label,fontsize=10,color='#435a70');cb.ax.tick_params(labelsize=9,length=2)
  cb.outline.set_visible(False)
 fig.subplots_adjust(left=.055,right=.96,top=.88,bottom=.17,wspace=.07,hspace=.33)
 fig.text(.06,.105,'Červený obrys: Semily. Šedá u lesů: pokrytí pod 95 %. Půdní průměry se týkají plochy s platnou predikcí.',fontsize=10,color='#435a70')
 fig.text(.06,.061,'Zdroje: Bedrunka / UPOL · LUCC Czechia / PřF UK · ISRIC SoilGrids 2.0 · CShapes 2.0. Výpočty: okresní průniky a váhy.',fontsize=9,color='#435a70')
 fig.text(.06,.035,'Lesy 1845 jsou plošný odhad ze zdrojových jednotek; půda není měření roku 1930; CShapes zachycuje generalizované státní hranice.',fontsize=9,color='#435a70')
 fig.savefig(FIG/'GIS_v06_new_layers_judicial_1930.png',dpi=190,facecolor=fig.get_facecolor())
 fig.savefig(FIG/'GIS_v06_new_layers_judicial_1930.pdf',dpi=300,facecolor=fig.get_facecolor())
 plt.close(fig)
 print(str(FIG/'GIS_v06_new_layers_judicial_1930.png'),flush=True)

if __name__=='__main__':main()
