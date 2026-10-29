"""CP uses the approved FT implementation, including small-n and zero-IQR cases."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[3]
KIT = ROOT/'engines'


def fixture(folder, lot='L1', product='P1', upper='5', condition='VGS=10V'):
    folder.mkdir(parents=True, exist_ok=True)
    def write(name, rows):
        with (folder/name).open('w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerows(rows)
    write(lot+'_cleaned_1.csv', [['Lot_ID','Wafer_ID','Bin','P','I','Flat'],
        *[[lot,'01',2 if p==100 else 1,p,i,0] for p,i in zip([0,10,20,100,'over22'],[1e-9,2e-9,3e-9,100e-9,''])]])
    write(lot+'_spec_1.csv', [['Parameter','P','I','Flat'],['Unit','V','A','V'],
        ['LimitL','-1','0','0'],['LimitU',upper,'5e-8','1'],['TestCond',condition,'VGS=0','VDS=0']])
    write(lot+'_yield_1.csv', [['Lot_ID','Product_Name'],[lot,product]])


def run(folder, output, package=None):
    output.mkdir(exist_ok=True)
    package = package or KIT/'packages/native.pyz'
    env = {**os.environ,'PYTHONUTF8':'1','STUDIO_FT_PAT_PACKAGE':str(package),
           'STUDIO_FT_PAT_SHA256':hashlib.sha256((KIT/'packages/native.pyz').read_bytes()).hexdigest()}
    program = "import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from local_cp_ft_pat import generate_cp_ft_pat;print(generate_cp_ft_pat('TEST',Path(sys.argv[2]),Path(sys.argv[3])))"
    return subprocess.run([str(KIT/'runtime/python.exe'),'-s','-B','-c',program,
        str(ROOT/'engine_support/desktop_client/nce_desktop'),str(folder),str(output)],
        env=env,capture_output=True,text=True,encoding='utf8',timeout=90)


def test_ft_linear_quantiles_zero_iqr_small_n_fail_bin_and_small_units(tmp_path):
    inputs=tmp_path/'data';fixture(inputs)
    done=run(inputs,tmp_path/'files')
    assert done.returncode==0,done.stdout+done.stderr
    manifest=json.loads((tmp_path/'PAT_source_manifest.json').read_text(encoding='utf8'))
    assert manifest['statistics_module']=='shared.pat_engine'
    assert manifest['record_count']==5 and manifest['parameter_count']==3
    assert manifest['parameters']['I']['display_unit']=='nA'
    book=openpyxl.load_workbook(next((tmp_path/'files').glob('*.xlsx')),data_only=True)
    rows={r[0]:r for r in list(book.active.values)[2:]};book.close()
    p=rows['P (V)'];assert p[1]==4 and p[5:9]==(7.5,15,40,100)
    assert p[9]==pytest.approx(32.5/1.35,abs=1e-6)
    assert p[10]==pytest.approx(15-6*32.5/1.35,abs=1e-6)
    assert p[14:]==(None,None,None) # FT leaves manual updates blank.
    assert rows['Flat (V)'][9:12]==(0,0,0) # No old CP minimum-IQR floor.
    assert rows['I (nA)'][1]==4 and rows['I (nA)'][8]==100
    assert rows['I (nA)'][12:14]==(0,50)


@pytest.mark.parametrize('change',[{'upper':'6'},{'condition':'VGS=12V'},{'product':'OTHER'},{'product':''}])
def test_incompatible_specs_conditions_or_product_cannot_pool(tmp_path,change):
    folder=tmp_path/'data';fixture(folder);fixture(folder,lot='L2',**change)
    done=run(folder,tmp_path/'files')
    assert done.returncode!=0 and not list((tmp_path/'files').glob('*.xlsx'))
    assert '不兼容' in done.stderr or '产品身份' in done.stderr


def test_compatible_lots_pool_without_dropping_repeated_values(tmp_path):
    folder=tmp_path/'data';fixture(folder);fixture(folder,lot='L2')
    done=run(folder,tmp_path/'files');assert done.returncode==0,done.stderr
    manifest=json.loads((tmp_path/'PAT_source_manifest.json').read_text(encoding='utf8'))
    assert manifest['lots']==['L1','L2'] and manifest['record_count']==10
    book=openpyxl.load_workbook(next((tmp_path/'files').glob('*.xlsx')),data_only=True)
    assert list(book.active.values)[2][1]==8;book.close()


def test_wrong_ft_package_is_rejected(tmp_path):
    fixture(tmp_path/'data');bad=tmp_path/'wrong.pyz';bad.write_bytes(b'wrong')
    done=run(tmp_path/'data',tmp_path/'files',bad)
    assert done.returncode!=0 and '校验失败' in done.stderr
    assert not list((tmp_path/'files').glob('*.xlsx'))


def test_jetech_lot_alias_and_metadata_columns_are_not_measurements(tmp_path):
    folder=tmp_path/'data';fixture(folder)
    p=folder/'L1_cleaned_1.csv'
    rows=list(csv.reader(p.open(encoding='utf-8-sig')));rows[0][0]='LotID'
    for row in rows:row.append('TEST_NUM' if row is rows[0] else '3')
    with p.open('w',newline='',encoding='utf-8-sig') as f:csv.writer(f).writerows(rows)
    p=folder/'L1_spec_1.csv';rows=list(csv.reader(p.open(encoding='utf-8-sig')))
    for row in rows:row.append('TEST_NUM' if row is rows[0] else '')
    with p.open('w',newline='',encoding='utf-8-sig') as f:csv.writer(f).writerows(rows)
    done=run(folder,tmp_path/'files');assert done.returncode==0,done.stderr
    manifest=json.loads((tmp_path/'PAT_source_manifest.json').read_text(encoding='utf8'))
    assert manifest['lots']==['L1'] and list(manifest['parameters'])==['P','I','Flat']


def test_guoyu_spec_labels_and_source_lot_survive_shifted_header_rows(tmp_path):
    raw=tmp_path/'EDS';raw.mkdir();path=raw/'01#-759.xlsx'
    book=openpyxl.Workbook();sheet=book.active
    sheet.cell(1,1,'JUNO Test System DTS-2000')
    for row,label,value,col in [(8,'LotName','25B103',3),(13,'WaferID',1,2),
                                (14,'Devices',4,2),(15,'Pass',3,2),(16,'Fail',1,2)]:
        sheet.cell(row,1,label);sheet.cell(row,col,value)
    sheet.cell(20,1,'Bias1');sheet.cell(20,5,'IE=1mA')
    sheet.cell(23,1,'Min Limit');sheet.cell(24,1,'Max Limit');sheet.cell(25,1,'Average')
    lows=['0mV',None,'710V','710V',None,'1.2V','0nA']
    highs=['20mV','200nA','850V','850V','6','1.65V','200nA']
    for col,(low,high) in enumerate(zip(lows,highs),5):
        if low is not None:sheet.cell(23,col,low)
        sheet.cell(24,col,high);sheet.cell(25,col,'1.129')
    headers=['Serial#','Bin#','X','Y','1 CONT2','2 IR','3 VZ1','4 VZ2','5 DELTA','6 VF','7 IR']
    units=['','','','','mV','nA','V','V','','V','nA']
    for col,(header,unit) in enumerate(zip(headers,units),1):
        sheet.cell(34,col,header)
        if unit:sheet.cell(35,col,unit)
    for i in range(4):
        data=[('P' if i<3 else 'F')+str(i+1),1 if i<3 else 2,0,0,1.13+i/100,6.2,758,761.7,3.7,1.491,8.9]
        for col,value in enumerate(data,1):sheet.cell(36+i,col,value)
    book.save(path);book.close()
    stage=tmp_path/'stage';stage.mkdir();out=stage/'files';out.mkdir();intermediate=stage/'standard';intermediate.mkdir()
    package=KIT/'packages/native.pyz'
    env={**os.environ,'PYTHONUTF8':'1','STUDIO_FT_PAT_PACKAGE':str(package),
         'STUDIO_FT_PAT_SHA256':hashlib.sha256(package.read_bytes()).hexdigest()}
    program="import sys;from pathlib import Path;sys.path[:0]=sys.argv[1:3];from local_guoyu_pat_input import prepare_guoyu_pat;from local_cp_ft_pat import generate_cp_ft_pat;prepare_guoyu_pat([Path(sys.argv[3])],Path(sys.argv[4]));generate_cp_ft_pat('GUOYU',Path(sys.argv[4]),Path(sys.argv[5]))"
    done=subprocess.run([str(KIT/'runtime/python.exe'),'-s','-B','-c',program,
        str(ROOT/'engine_support/desktop_client/nce_desktop'),str(KIT/'packages/cp.pyz'),
        str(path),str(intermediate),str(out)],env=env,capture_output=True,text=True,encoding='utf8',timeout=90)
    assert done.returncode==0,done.stdout+done.stderr
    manifest=json.loads((stage/'PAT_source_manifest.json').read_text(encoding='utf8'))
    assert manifest['lots']==['25B103'] and manifest['record_count']==4
    assert manifest['parameters']['CONT2[mV]']['lsl']==0
    assert manifest['parameters']['CONT2[mV]']['usl']==20
