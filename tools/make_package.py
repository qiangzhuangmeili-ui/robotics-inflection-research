"""Create a portable package ZIP with standard-library Python; never includes inbox or credentials."""
import argparse
import csv
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))

def build(package_id, include_sources=False):
    entries = {r['package_id']:r for r in rows(ROOT/'data/package_index.csv')}
    if package_id not in entries:
        raise ValueError('Unknown package ID')
    package = ROOT/'packages'/package_id
    companies = rows(package/'assignment.csv')
    ids = {r['security_id'] for r in companies}
    codes = {r['stock_code'] for r in companies}
    destination = ROOT/'deliveries'/f'{package_id}.zip'
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ['AGENTS.md','PROJECT_STATE.json','data/resource_map.csv']:
            archive.write(ROOT/name, name)
        for folder in ['docs','templates']:
            for path in sorted((ROOT/folder).glob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(ROOT).as_posix())
        for path in sorted(package.rglob('*')):
            if path.is_file() and path.suffix in {'.csv','.md','.json'}:
                archive.write(path, path.relative_to(ROOT).as_posix())
        for path in sorted((ROOT/'archive').rglob('*')):
            if path.suffix == '.csv':
                original = rows(path)
                if not original or 'security_id' not in original[0]:
                    continue
                selected = [r for r in original if r['security_id'] in ids]
                if not selected:
                    continue
                output = io.StringIO(newline='')
                writer = csv.DictWriter(output, fieldnames=list(original[0]))
                writer.writeheader()
                writer.writerows(selected)
                archive.writestr(path.relative_to(ROOT).as_posix(), '\ufeff'+output.getvalue())
            elif path.suffix in {'.md','.json'}:
                archive.write(path,path.relative_to(ROOT).as_posix())
        for data_file in ['company_master.csv','manual_requests.csv','financial_gaps.csv']:
            path=ROOT/'data'/data_file
            original=rows(path)
            if original:
                output=io.StringIO(newline='')
                writer=csv.DictWriter(output,fieldnames=list(original[0]))
                writer.writeheader()
                writer.writerows(r for r in original if r['security_id'] in ids)
                archive.writestr('data/'+data_file,'\ufeff'+output.getvalue())
        output=io.StringIO(newline='')
        writer=csv.DictWriter(output,fieldnames=list(entries[package_id]))
        writer.writeheader()
        writer.writerow(entries[package_id])
        archive.writestr('data/package_index.csv','\ufeff'+output.getvalue())
        included=[]
        if include_sources:
            for code in sorted(codes):
                folder=ROOT/'sources'/code
                if folder.is_dir():
                    for path in sorted(folder.glob('*.pdf')):
                        archive.write(path,path.relative_to(ROOT).as_posix())
                        included.append(path.relative_to(ROOT).as_posix())
        archive.writestr('START_HERE.md',f'''# 本包从这里开始

只执行 packages/{package_id}/TASK.md 与 assignment.csv。此ZIP为单包附件，data和archive的公司行已经裁剪到本包，不能拿包内数量替代全池1054家统计。

只上传附件不会授权全池调查。若收到此包，先读任务卡和docs/执行规则.md。

包含PDF：{len(included)}份。没有PDF只表示尚未随包附上原文；仓库和历史URL可能需要访问权限。缺文件请列明确标题、证券代码和报告期，等待用户补件。

resource_map中的哈希属于完整原始快照；本ZIP已按公司裁剪的CSV不能与原始完整表哈希直接比较。目录列表中的绝对路径只是历史位置，不表示云端可读。
''')
        archive.writestr('attachment_manifest.json',json.dumps({'package_id':package_id,'company_count':len(companies),'pdf_count':len(included),'pdf_paths':included,'scope':'ONLY_THIS_PACKAGE','state':'PREPARED_NOT_EXECUTED'},ensure_ascii=False,indent=2))
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('package_id',help='package ID or --all is not used; use ALL to build all')
    parser.add_argument('--include-sources',action='store_true',help='include only matching sources/<six-digit-code>/*.pdf; inbox never included')
    args=parser.parse_args()
    selected=[r['package_id'] for r in rows(ROOT/'data/package_index.csv')] if args.package_id=='ALL' else [args.package_id]
    for pid in selected:
        path=build(pid,args.include_sources)
        print(path.name)
