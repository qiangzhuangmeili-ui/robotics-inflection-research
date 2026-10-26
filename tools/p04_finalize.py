"""P04 收尾：写 manifest.json / review.json，并回写状态源（active_issue、PROJECT_STATE、执行计划）。

只改调度状态字段，不改任何历史统计、不改旧包状态、不改他人结果。
"""
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'runs/issues/P04'
NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
COMMIT_BEFORE = 'c5ce8b3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_manifest(exclude=('manifest.json',)):
    files = []
    for p in sorted(OUT.glob('*')):
        if p.is_file() and p.name not in exclude:
            files.append({'path': f'runs/issues/P04/{p.name}', 'bytes': p.stat().st_size, 'sha256': sha(p)})
    for p in sorted((ROOT / 'tools').glob('p04_*.py')):
        files.append({'path': f'tools/{p.name}', 'bytes': p.stat().st_size, 'sha256': sha(p)})
    manifest = {
        'issue_key': 'P04',
        'issue_number': 15,
        'plan_version': '20261026_collection_first_v2',
        'generated_at': NOW,
        'executor': 'WorkBuddy AI',
        'base_commit': COMMIT_BEFORE,
        'review_nature': 'SELF_CHECK',
        'files': files,
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return files


def build_review(files):
    sc = json.loads((OUT / 'self_check.json').read_text(encoding='utf-8'))
    rules = json.loads((OUT / 'period_conversion_rules.json').read_text(encoding='utf-8'))
    mapping = list(csv.DictReader((OUT / 'provider_field_mapping.csv').open(encoding='utf-8')))
    gaps = list(csv.DictReader((OUT / 'legacy_snapshot_gap_register.csv').open(encoding='utf-8')))
    fdict = list(csv.DictReader((OUT / 'financial_field_dictionary.csv').open(encoding='utf-8')))
    review = {
        'template_only': False,
        'plan_version': '20261026_collection_first_v2',
        'issue_number': 15,
        'issue_key': 'P04',
        'executor': 'WorkBuddy AI',
        'reviewer': 'WorkBuddy AI',
        'review_method': 'SELF_CHECK_REPRODUCIBLE_CHECKS_AND_LIVE_PROBES',
        'reviewed_at': NOW,
        'decision': sc['decision'],
        'dependency_review': {
            'key': 'P00',
            'review_file': 'runs/issues/P00/review.json',
            'decision': 'SELF_CHECK_PASS',
        },
        'checks': [
            {
                'criterion': '收入/扣非/净利、金额/比例/百分点均不混；NULL和真实0可区分',
                'result': 'PASS',
                'evidence': ['financial_field_dictionary.csv', 'self_check.json#A1-A3',
                             'legacy_snapshot_gap_register.csv'],
                'detail': '33 个字段逐一标注 unit_kind（AMOUNT_CNY/RATIO_PCT/DELTA_PP/RATIO_TIMES/DATE/CODE）与 scale；'
                          '收入、扣非归母、归母净利为三个独立 field_id 且各自写明不得互相替代；'
                          '旧快照 41 个金额列零值单元格=0、62 家缺失行全列 NULL，NULL 与真实 0 可区分；'
                          '每个字段均有 null_semantics。',
            },
            {
                'criterion': '旧快照缺 2025H1 营收、经营现金流等具体缺口已列；来源字段映射有证据',
                'result': 'PASS',
                'evidence': ['legacy_snapshot_gap_register.csv', 'provider_field_mapping.csv',
                             'crosscheck_provider_vs_pdf.json', 'crosscheck_period_conversion.json'],
                'detail': '缺口登记 63 行：41 列逐列覆盖 + 18 项整列缺失 + 2 项列存在但不可用 + 北交所分段缺口 + '
                          '62 家缺失原因不可判；其中 2025H1 五项基数缺口单独成行。'
                          '映射 52 行全部带 evidence_ref：新浪为 9 次实测探针，官方 PDF 为物理页码，'
                          '旧快照为与官方 PDF 的逐项数值比对，缺失字段用全字段扫描作为负证据。',
            },
        ],
        'self_check_summary': sc['summary'],
        'coverage': {
            'probed_companies': 3,
            'probed_exchanges': ['SH', 'SZ', 'BJ'],
            'probed_provider_fields': 281,
            'pdf_documents_read': 4,
            'pdf_line_items_located': sum(1 for r in json.loads((OUT / 'pdf_lineitem_evidence.json')
                                                                .read_text(encoding='utf-8'))['line_items']
                                          if r['status'] == 'FOUND'),
            'canonical_fields': len(fdict),
            'mapping_rows': len(mapping),
            'gap_rows': len(gaps),
            'full_universe_processed': 0,
            'companies_screened': 0,
        },
        'key_findings': [
            '结构化接口无扣非归母净利润字段（77 个利润表字段全量扫描），必须回官方 PDF',
            '接口 type=0/1/2/3/4 为报告期类型选择，返回均为年初至今累计，不提供单季度序列',
            '官方年报“分季度主要财务数据”表直接披露单季，优先于累计相减',
            '旧快照 22 列扣非为累计口径（P02 记为“单季”有误），已用逐季加总证明',
            '旧快照对北交所覆盖率 0/62，与 P03 旧工作台 BJ=400 相互印证',
            '62 家缺失原因不可判（listing_date 全 UNKNOWN、prelisting_flag 全 NONE）',
            '2025H1 五项基数缺失，导致 2026H1 同比全部不可计算',
            '毛利率为百分数数值（23.28 表示 23.28%），比率变动另用百分点',
        ],
        'allows_next_stage': True,
        'allows_next_stage_scope': 'P05(#16) 的 P04 依赖成立；P07(#18) 仍需 P05、P06 各自验收',
        'next_recommended_issue': {'number': 16, 'key': 'P05'},
        'limitations': [
            '3 家公司 4 份 PDF 的样本，不等于全池口径验收',
            '新浪为非官方结构化数据；只证明数值与单位对齐，不证明业务口径正确',
            'PDF 数值来自文本抽取，3 份 PDF 的“基本每股收益”标签未识别，已如实记 LABEL_NOT_FOUND_IN_RANGE',
            '旧工作台 /api/finance/report 未纳入映射（字段词汇未实测）',
            'SELF_CHECK，不是独立审计',
        ],
        'artifacts': {f['path']: f['sha256'] for f in files},
    }
    (OUT / 'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return review


def update_active_issue(review):
    path = ROOT / 'data/active_issue.json'
    cur = json.loads(path.read_text(encoding='utf-8'))
    prev = cur.get('last_completed')
    cur.update({
        'active_issue_number': None,
        'active_issue_key': None,
        'executor': None,
        'started_at': None,
        'status': 'IDLE_P04_SELF_CHECK_PASS',
        'next_recommended_issue_number': 16,
        'next_recommended_issue_key': 'P05',
        'next_recommended_reason': 'P04 已冻结字段/单位/报表/时间口径并给出52条来源映射；P05 采集器所需的字段口径与校验规则已具备。',
        'last_completed': {
            'issue_number': 15,
            'issue_key': 'P04',
            'completed_at': NOW,
            'review_file': 'runs/issues/P04/review.json',
            'decision': review['decision'],
            'allows_next_stage_scope': review['allows_next_stage_scope'],
            'canonical_fields': review['coverage']['canonical_fields'],
            'mapping_rows': review['coverage']['mapping_rows'],
            'gap_rows': review['coverage']['gap_rows'],
        },
        'previous_completed': prev,
        'p02_completed': cur.get('previous_completed'),
        'open_followups_from_P04': [
            '扣非归母净利润只能回官方 PDF 取，采集器必须解析非经常性损益表或主要会计数据表。',
            '北交所 62 家旧快照覆盖率 0/62，必须走 P03 显式三市场适配器。',
            '2025H1 五项基数缺失，2026H1 同比在补齐前不可计算。',
            'listing_date 1054/1054 UNKNOWN，P05 须回填后才能判定上市前不适用。',
            '旧快照 22 列扣非为累计口径，S00 标准化须按累计读入（P02 表述待更正）。',
        ],
    })
    cur['note'] = ('P04 为 SELF_CHECK 口径冻结，未做任何财务筛选与业务判断。'
                   '全池采集仍未启动；业务证据未新增独立验收。')
    path.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def update_project_state(review):
    path = ROOT / 'PROJECT_STATE.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    plan = state.setdefault('issue_plan', {})
    plan['last_completed_issue'] = {
        'issue_number': 15,
        'issue_key': 'P04',
        'completed_at': NOW,
        'review_file': 'runs/issues/P04/review.json',
        'decision': review['decision'],
        'allows_next_stage_scope': review['allows_next_stage_scope'],
        'canonical_fields': review['coverage']['canonical_fields'],
        'mapping_rows': review['coverage']['mapping_rows'],
        'gap_rows': review['coverage']['gap_rows'],
        'self_check_passed': f"{review['self_check_summary']['pass']}/{review['self_check_summary']['total']}",
    }
    plan['next_recommended_issue'] = 'https://github.com/qiangzhuangmeili-ui/robotics-inflection-research/issues/16'
    plan['active_issue'] = None
    plan['p04_field_contract'] = {
        'status': 'FROZEN',
        'version': 'P04_FIELD_CONTRACT_V1',
        'field_dictionary': 'runs/issues/P04/financial_field_dictionary.csv',
        'provider_mapping': 'runs/issues/P04/provider_field_mapping.csv',
        'period_rules': 'runs/issues/P04/period_conversion_rules.json',
        'gap_register': 'runs/issues/P04/legacy_snapshot_gap_register.csv',
        'canonical_fields': review['coverage']['canonical_fields'],
        'mapping_rows': review['coverage']['mapping_rows'],
        'verified_numeric_match_provider_vs_pdf': '14/14',
        'verified_period_conversion_checks': '48/48',
        'review_nature': 'SELF_CHECK',
        'must_fix_downstream': [
            '扣非只能回官方 PDF',
            '北交所必须走显式三市场适配器',
            '2025H1 基数缺失导致 2026H1 同比不可算',
            '旧快照 22 列扣非为累计口径',
        ],
    }
    state['status'] = 'P04_FIELD_CONTRACT_FROZEN_SELF_CHECK_PASS'
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def update_plan_csv():
    path = ROOT / 'data/issue_execution_plan.csv'
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())
    changed = []
    for r in rows:
        if r['key'] == 'P04':
            r['status'] = 'SELF_CHECK_PASS'
            changed.append('P04→SELF_CHECK_PASS')
        elif r['key'] == 'P05':
            r['status'] = 'READY'
            changed.append('P05→READY')
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return changed


def main():
    files = build_manifest(exclude=('manifest.json', 'review.json'))
    review = build_review(files)
    files = build_manifest()
    update_active_issue(review)
    update_project_state(review)
    changed = update_plan_csv()
    print(json.dumps({'files': len(files), 'decision': review['decision'], 'plan_csv': changed,
                      'next': 'P05 #16'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
