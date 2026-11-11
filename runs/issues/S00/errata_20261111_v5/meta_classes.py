#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""元数据字段的影响分类（唯一来源，生产与自检共用）

第七轮 E 项：C24 原先直接读台账里的 `class` 列，把「实质字段」标成
`REGISTERED_DISPLAY_ONLY` 就能绕过内容审查。分类必须由字段名锁定，
台账自报的 class 只能用来核对，不能用来决定是否放行。
"""

AFFECTS_VALUE = {
    "value_raw", "value_before_adoption", "unit_raw", "unit_scale",
    "currency", "period_source", "version_used", "original_document_id",
}
AFFECTS_QUALIFICATION = {
    "upstream_hold_fields", "low_base_flag", "comparability_note", "quarterly_inputs",
}
AFFECTS_TIMING_OR_PROVENANCE = {"published_on", "source_kind", "adoption_reason"}
AFFECTS_TRACE_LOCATION = {"source_page"}
AFFECTS_ADOPTION_EXPLANATION = {"evidence_label"}
AFFECTS_PROVENANCE = {"slot_id"}
AFFECTS_QUALIFICATION_REASON = {"status_reason"}

GROUPS = {
    "AFFECTS_VALUE": AFFECTS_VALUE,
    "AFFECTS_QUALIFICATION": AFFECTS_QUALIFICATION,
    "AFFECTS_TIMING_OR_PROVENANCE": AFFECTS_TIMING_OR_PROVENANCE,
    "AFFECTS_TRACE_LOCATION": AFFECTS_TRACE_LOCATION,
    "AFFECTS_ADOPTION_EXPLANATION": AFFECTS_ADOPTION_EXPLANATION,
    "AFFECTS_PROVENANCE": AFFECTS_PROVENANCE,
    "AFFECTS_QUALIFICATION_REASON": AFFECTS_QUALIFICATION_REASON,
}

CLASS_OF = {}
for _name, _fields in GROUPS.items():
    for _f in _fields:
        CLASS_OF[_f] = _name


def expected_class(meta_field):
    """按字段名锁定影响类别；未登记的一律视为展示字段。"""
    return CLASS_OF.get(meta_field, "DISPLAY_ONLY")


def is_substantive(meta_field):
    return expected_class(meta_field) != "DISPLAY_ONLY"
