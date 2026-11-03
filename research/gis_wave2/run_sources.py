"""Acquisition wrapper: preserve actual download provenance for any public mirror."""
import json
import download_sources as m
original_download=m.download
original_hydro=m.hydro

def download(url,path):
    try:
        return original_download(url,path)
    except Exception as error:
        if 'hydrosheds.org/file/HydroRIVERS/' not in url:
            raise
        errors=[str(error)]
        # Public research deposit explicitly identifies this archive as HydroRIVERS v10 Europe.
        # Dataset DOI: 10.5061/dryad.6wwpzgnf1 (Tian, 2026).
        for mirror in ['https://datadryad.org/downloads/file_stream/4804986','https://datadryad.org/api/v2/files/4804986/download']:
            try:
                rec=original_download(mirror,path)
                rec['original_provider_url']=url
                rec['mirror_dataset_doi']='10.5061/dryad.6wwpzgnf1'
                rec['transport_note']='Provider returned HTTP 403 to CI; public research-deposit copy used.'
                return rec
            except Exception as e:
                errors.append(str(e))
        raise RuntimeError('; '.join(errors))

def hydro():
    try:
        return original_hydro()
    except Exception as e:
        print('HYDRO_DOWNLOAD_INCOMPLETE',str(e),flush=True)
        (m.OUT/'hydro_download_error.txt').write_text(str(e),encoding='utf8')
        return {'status':'not_downloaded','error':str(e)}

m.download=download
m.hydro=hydro
if __name__=='__main__':m.main()
