"""Reject ownership inventories, private paths and game package/license metadata."""
import json,re,argparse
from pathlib import Path
from pipeline import ROOT,read,write

FORBIDDEN={'local_full_game_ids','full_game_ids','source_inventory_sha256','local_full_game','archive_path','archivepath','pkg_url','package_url','license_key','zrif','rif','ownership','owned_games','game_paths','client_secret','twitch_client_secret','igdb_client_secret','access_token','refresh_token','authorization','client-id','client_id','twitch_client_id'}
PRIVATE_PATH=re.compile(r'(?i)(?:(?<![a-z0-9])[a-z]:[\\/]|file://|\\\\[a-z0-9])')
GAME_URL=re.compile(r'(?i)https?://[^\s"<>]*(?:\.pkg(?:\?|$)|zeus\.dl\.playstation|ares\.dl\.playstation)')

def walk(value,path,errors):
    if isinstance(value,dict):
        for k,v in value.items():
            if k.casefold() in FORBIDDEN:errors.append(f'{path}: forbidden inventory/package field {k}')
            walk(v,f'{path}.{k}',errors)
    elif isinstance(value,list):
        for i,v in enumerate(value):walk(v,f'{path}[{i}]',errors)
    elif isinstance(value,str):
        if PRIVATE_PATH.search(value):errors.append(f'{path}: absolute/private filesystem path')
        if GAME_URL.search(value):errors.append(f'{path}: game package/download URL')

def main(compare_secrets_file=None):
    errors=[];files=[p for p in ROOT.rglob('*.json') if '.git' not in p.parts and p.name!='privacy-audit.json']
    for p in files:walk(read(p),p.relative_to(ROOT).as_posix(),errors)
    secret_scan=None
    if compare_secrets_file:
        from expand_igdb_metadata import credentials
        values=credentials(compare_secrets_file);text_files=[p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.parts and p.suffix in ('.py','.json','.md','.txt')]
        hits=[]
        for p in text_files:
            data=p.read_bytes()
            if any(value.encode('utf-8') in data for value in values):hits.append(p.relative_to(ROOT).as_posix())
        if hits:errors.append('Actual credential material found in public text files: '+', '.join(hits))
        secret_scan={'text_files_checked':len(text_files),'actual_credential_values_detected':len(hits),'configuration_or_values_persisted':False}
    if errors:raise ValueError('\n'.join(errors[:20]))
    result={'status':'passed','json_files_checked':len(files),'checks':['no ownership ID lists or inventory hashes','no absolute filesystem or archive paths','no game package URLs or license-key fields'],'private_inventory_policy':'Optional ownership data and detailed local coverage must stay outside the cover repository.'}
    if secret_scan:result['memory_only_actual_secret_comparison']=secret_scan
    write(ROOT/'privacy-audit.json',result);print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--compare-secrets-file',type=Path);args=p.parse_args();main(args.compare_secrets_file)
