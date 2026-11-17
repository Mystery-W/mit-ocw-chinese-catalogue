"""Build a bilingual, portable OCW catalogue from the completed capture.

This module performs no network calls. CSV is UTF-8 with BOM for Excel; JSON
retains structured fields, and the standalone HTML embeds its data so file://
opening works on another computer without Python or a web server.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from lxml import html

from crawl_ocw import BASE, clean, now, save_json

ROOT = Path(__file__).resolve().parent
FEATURE_ZH = dict(line.split("|", 1) for line in """Activity Assignments|活动作业
Activity Assignments with Examples|活动作业及示例
Competition Videos|竞赛视频
Demonstration Audio|演示音频
Demonstration Videos|演示视频
Design Assignments|设计作业
Design Assignments with Examples|设计作业及示例
Editable Files|可编辑文件
Exam Solutions|考试解答
Exams|考试
Image Gallery|图片集
Instructor Insights|教师教学经验
Laboratory Assignments|实验作业
Lecture Audio|授课音频
Lecture Notes|讲义
Lecture Videos|授课视频
Media Assignments|媒体作业
Media Assignments with Examples|媒体作业及示例
Multiple Assignment Types|多种作业
Multiple Assignment Types with Solutions|多种作业及解答
Music Audio|音乐音频
Open Textbooks|开放教材
Other Audio|其他音频
Other Video|其他视频
Podcasts|播客
Presentation Assignments|展示作业
Presentation Assignments with Examples|展示作业及示例
Problem Set Solutions|习题解答
Problem Sets|习题集
Problem-solving Notes|解题笔记
Problem-solving Videos|解题视频
Programming Assignments|编程作业
Programming Assignments with Examples|编程作业及示例
Projects|项目
Projects with Examples|项目及示例
Readings|阅读资料
Simulation Videos|仿真视频
Student Work|学生作品
Supplemental Exam Materials|考试补充材料
Tutorial Videos|辅导视频
Video Materials|视频资料
Videos|视频
Workshop Videos|工作坊视频
Written Assignments|书面作业
Written Assignments with Examples|书面作业及示例""".splitlines())

CATEGORY_RULES = {
    "A 授课视频": "官方标注 Lecture Videos，或课程导航明确为 Lecture Videos/Video Lectures/Class Videos。未核验整套视频完整性及逐个播放。",
    "B 其他教学视频": "有演示、辅导、解题、实验或其他视频标注/明确导航；不据此宣称有完整课堂录像。",
    "C 授课音频": "官方标注 Lecture Audio，且未发现授课或其他教学视频证据。",
    "D 讲义或开放教材": "官方标注讲义/开放教材/解题笔记，或导航提供相应入口；也可能含作业、阅读等。",
    "E 作业、阅读或其他学习资料": "有作业、考试、项目、阅读、作品、非授课音频等学习材料证据。",
    "F 外部课程或资源入口": "课程导航的实质学习内容主要链接站外；外部是否免费、可注册及可播放未逐一核验。",
    "G 大纲或介绍性资料": "课程首页可访问，但导航与资源标签只足以确认大纲、日历或教学介绍。不能据此断言没有其他材料。",
    "H 已退役，转至档案库": "官网明确说明课程已从 OCW 退役，并提供 DSpace 档案入口；档案下载与播放未逐项验证。",
    "U 无法确定": "抓取失败或证据不足；不将未知状态误判为不开放。",
}


def is_internal(url: str) -> bool:
    """Identify OCW-hosted evidence; other MIT domains remain external platforms."""
    return urlparse(url).hostname == "ocw.mit.edu"


def classify(record: dict, features: list[str]) -> dict:
    """Make a transparent resource classification, separate from academic level.

    Positive labels indicate published evidence, not successful video playback.
    All-external navigation is classified as an external entry even if metadata
    promises videos; individual resource flags still retain that promise.
    """
    links = record.get("resource_links", [])
    substantive = [x for x in links if not re.search(r"instructor insights|^syllabus$|^calendar$|^course home$|^about", x["label"], re.I)]
    external_only = bool(links) and not any(is_internal(x["url"]) for x in (substantive or links))
    learning_links = [x for x in links if "instructor-insights" not in x["url"]]
    lecture_links = [x for x in learning_links if re.search(r"lecture.*video|video.*lecture|class videos|video lectures", x["label"], re.I)]
    video_links = [x for x in learning_links if re.search(r"video|lecture collection", x["label"], re.I)
                   and not re.search(r"instructor insights|about.*course|introduction video|welcome video", x["label"], re.I)]
    lecture = "Lecture Videos" in features or bool(lecture_links)
    video = any("video" in f.lower() for f in features) or bool(video_links)
    audio = "Lecture Audio" in features
    notes = any(f in features for f in ("Lecture Notes", "Open Textbooks", "Problem-solving Notes"))
    notes = notes or any(re.search(r"lecture notes|lecture slides|lecture handouts|textbook|course notes", x["label"], re.I) for x in links)
    other_materials = any(f != "Instructor Insights" for f in features)
    other_materials = other_materials or any(re.search(r"assignment|problem set|reading|exam|project|lab|resource|download|text|audio|podcast", x["label"], re.I) for x in substantive)
    if record.get("status") != "ok":
        category = "U 无法确定"
    elif external_only:
        category = "F 外部课程或资源入口"
    elif lecture:
        category = "A 授课视频"
    elif video:
        category = "B 其他教学视频"
    elif audio:
        category = "C 授课音频"
    elif notes:
        category = "D 讲义或开放教材"
    elif other_materials:
        category = "E 作业、阅读或其他学习资料"
    elif links:
        category = "G 大纲或介绍性资料"
    else:
        category = "U 无法确定"
    galleries = [x for x in learning_links if "/video_galleries/" in x["url"]]
    lesson_links = [x for x in learning_links if re.search(r"lecture|session|class\s*\d|unit\s*\d|module|workshop content", x["label"], re.I)]
    selected = (lecture_links or galleries or video_links or (lesson_links if lecture or video else []) or substantive or links)[:1]
    return {"resource_category": category, "has_lecture_video": lecture,
            "has_other_video": any("video" in f.lower() and f != "Lecture Videos" for f in features) or (bool(video_links) and not lecture),
            "has_lecture_audio": audio, "has_notes": bool(notes), "external_only": external_only,
            "primary_resource_url": selected[0]["url"] if selected else "",
            "primary_resource_label": selected[0]["label"] if selected else "",
            "classification_basis": CATEGORY_RULES[category]}


def text_description(record: dict, metadata: dict, source: dict) -> str:
    """Prefer the visible complete description and retain source text elsewhere."""
    if record.get("description_text"):
        return record["description_text"]
    fragment = metadata.get("course_description_html", "")
    if fragment:
        return clean(html.fromstring(fragment).text_content())
    return (metadata.get("course_description") or source.get("short_description") or "").strip()


def build_rows() -> tuple[list[dict], dict]:
    """Join by canonical course URL, never by non-unique course code or title."""
    records = json.loads((ROOT / "course_records.json").read_text(encoding="utf-8"))
    source_courses = json.loads((ROOT / "sources/search_courses.json").read_text(encoding="utf-8"))
    sources = {urljoin(BASE, r["slug"]).rstrip("/") + "/": c for c in source_courses for r in c["runs"]}
    taxonomy = dict(line.split("\t", 1) for line in (ROOT / "taxonomy_zh.tsv").read_text(encoding="utf-8").splitlines())
    titles = json.loads((ROOT / "titles.json").read_text(encoding="utf-8"))
    translations = {}
    for path in sorted(ROOT.glob("translations_*.txt")):
        start = int(path.stem.split("_")[1])
        translated = path.read_text(encoding="utf-8").splitlines()
        assert len(translated) == min(250, len(titles) - start), path
        translations.update(zip(titles[start:start+len(translated)], translated))
    translations.update({"Carrier Systems": "承运系统", "Angles": "Angles（MIT 学生写作年刊）",
                         "Bestsellers: Out for the Count": "畅销书：寻找吸血鬼伯爵（Out for the Count）",
                         "Simplicity Theory": "简单理论（模型论）"})
    normalized = {clean(k): v for k,v in translations.items()}
    review_path = ROOT / "reviewed_resources.json"
    reviews = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    checks_path = ROOT / "resource_entry_checks.json"
    checks_list = json.loads(checks_path.read_text(encoding="utf-8")) if checks_path.exists() else []
    checks = {x["url"]: x for x in checks_list}
    save_json(ROOT / "title_translations.json", translations)
    rows, title_differences, missing_topics = [], [], set()
    for record in records:
        source = sources.get(record["url"], {})
        metadata = record.get("metadata", {})
        title = clean(metadata.get("course_title") or source.get("title", ""))
        source_title = source.get("title", "")
        if clean(source_title) != title:
            title_differences.append({"url": record["url"], "metadata_title": title, "search_title": source_title})
        zh = normalized.get(title) or translations.get(source_title, "")
        topics = metadata.get("topics", [])
        flattened = list(dict.fromkeys(t for path in topics for t in path)) or source.get("topics", [])
        missing_topics.update(t for t in flattened if t not in taxonomy)
        departments = record.get("departments") or source.get("department_name", [])
        features = metadata.get("learning_resource_types", source.get("course_feature_tags", [])) or []
        extra_codes = metadata.get("extra_course_numbers", "")
        if isinstance(extra_codes, list):
            extra_codes = "; ".join(extra_codes)
        description = text_description(record, metadata, source)
        external_links = [x for x in record.get("resource_links", []) if not is_internal(x["url"])]
        mooc_links = list(dict.fromkeys(record.get("mooc_links", []) + [x["url"] for x in external_links
            if any(domain in x["url"] for domain in ("edx.org", "mitxonline.mit.edu", "openlearninglibrary.mit.edu"))]))
        code = str(metadata.get("primary_course_number") or source.get("coursenum", ""))
        item = {"id": metadata.get("site_uid") or str(source.get("id", "")),
                "course_code": code, "extra_course_codes": extra_codes,
                "title_en": title, "title_zh": zh, "search_title_en": source_title,
                "translation_note": "AI辅助译名，非MIT官方中文名称；专业术语请结合英文原题核查",
                "entry_type": "开放资源/补充资源（RES）" if code.upper().startswith("RES") else "课程",
                "departments": departments, "departments_zh": [taxonomy.get(x,x) for x in departments],
                "topics": flattened, "topics_zh": [taxonomy.get(x,x) for x in flattened],
                "topic_paths": topics, "topic_paths_zh": [[taxonomy.get(x,x) for x in path] for path in topics],
                "top_topics": list(dict.fromkeys(path[0] for path in topics if path)),
                "top_topics_zh": list(dict.fromkeys(taxonomy.get(path[0],path[0]) for path in topics if path)),
                "features": features, "features_zh": [FEATURE_ZH.get(f,f) for f in features],
                "academic_level": metadata.get("level", []), "term": metadata.get("term", ""),
                "year": str(metadata.get("year", "")),
                "instructors": [i.get("title", "") for i in metadata.get("instructors", [])],
                "description_en": description, "description_original": metadata.get("course_description") or source.get("short_description", ""),
                "course_url": record["url"], "metadata_url": record["url"] + "data.json",
                "resource_links": record.get("resource_links", []), "external_links": external_links,
                "mooc_links": mooc_links, "download_links": record.get("download_links", []),
                "capture_status": record["status"], "captured_at": record.get("fetched_at", ""),
                "cache_key": record.get("cache_key", ""), **classify(record, features)}
        if record["url"] in reviews:
            item.update(reviews[record["url"]])
        item["video_evidence"] = item.get("video_evidence") or "; ".join(f for f in features if "video" in f.lower())
        if item["has_lecture_video"] and not item["video_evidence"]:
            item["video_evidence"] = "课程导航明确标示授课视频"
        checked = checks.get(item["primary_resource_url"])
        item["entry_check"] = (f"入口页面HTTP {checked['status']}；未验证媒体播放" if checked else "未单独核查入口页面；已读取课程首页")
        rows.append(item)
    rows.sort(key=lambda x: (x["course_code"],x["year"],x["course_url"]))
    audit = {"built_at": now(), "course_count": len(rows), "unique_codes": len({r["course_code"] for r in rows}),
             "distinct_english_titles": len({r["title_en"] for r in rows}),
             "missing_titles_zh": [r["course_url"] for r in rows if not r["title_zh"]],
             "missing_codes": [r["course_url"] for r in rows if not r["course_code"]],
             "missing_descriptions": [r["course_url"] for r in rows if not r["description_en"]],
             "missing_topics": sorted(missing_topics), "title_differences": title_differences,
             "resource_counts": dict(Counter(r["resource_category"] for r in rows)),
             "lecture_video_flag_count": sum(r["has_lecture_video"] for r in rows),
             "failed_captures": sum(r["capture_status"] != "ok" for r in rows),
             "resource_entry_checks": len(checks_list),
             "resource_entry_check_failures": sum(c["status"] != 200 for c in checks_list),
             "coverage": json.loads((ROOT / "coverage.json").read_text(encoding="utf-8"))}
    return rows, audit


def join(values: list) -> str:
    """Use a readable separator while preserving the structured original in JSON."""
    return "；".join(str(x) for x in values)


def table_row(row: dict) -> dict:
    """Expose requested fields first, followed by provenance and study filters."""
    return {"课程代码": row["course_code"], "课程标题（英文）": row["title_en"],
            "课程标题（中文辅助译名）": row["title_zh"], "学科类别（中文）": join(row["topics_zh"]),
            "开放学习内容类型": row["resource_category"], "课程介绍（官方英文全文）": row["description_en"],
            "课程链接": row["course_url"], "资源类型（官方标签译文）": join(row["features_zh"]),
            "资源类型（官方英文标签）": join(row["features"]),
            "有授课视频证据": "是" if row["has_lecture_video"] else "未发现",
            "有其他视频证据": "是" if row["has_other_video"] else "未发现",
            "有授课音频证据": "是" if row["has_lecture_audio"] else "未发现",
            "有讲义或教材证据": "是" if row["has_notes"] else "未发现",
            "主要学习入口": row["primary_resource_url"], "入口名称": row["primary_resource_label"],
            "外部MOOC或在线课程入口": join(row["mooc_links"]),
            "所属院系（中文）": join(row["departments_zh"]), "所属院系（英文）": join(row["departments"]),
            "学科路径（中文）": join([" > ".join(p) for p in row["topic_paths_zh"]]),
            "学科路径（英文）": join([" > ".join(p) for p in row["topic_paths"]]),
            "学术级别": join([{"Undergraduate":"本科","Graduate":"研究生","Non-Credit":"非学分"}.get(x,x) for x in row["academic_level"]]),
            "年份": int(row["year"]) if row["year"].isdigit() else row["year"], "学期": row["term"],
            "交叉课程代码": row["extra_course_codes"], "教师": join(row["instructors"]),
            "条目性质": row["entry_type"], "分类依据与限制": row["classification_basis"],
            "首页抓取状态": row["capture_status"], "抓取时间（UTC+08）": row["captured_at"],
            "元数据链接": row["metadata_url"], "中文译名说明": row["translation_note"],
            "主要入口核查状态": row["entry_check"]}


def main() -> None:
    """Produce complete user files and fail loudly on missing required records."""
    rows, audit = build_rows()
    save_json(ROOT / "validation.json", audit)
    assert len(rows) == audit["coverage"]["union_total"], "Incomplete capture"
    assert len({r["course_url"] for r in rows}) == len(rows), "Duplicate URLs"
    assert not audit["missing_titles_zh"], "Missing translations"
    assert not audit["missing_topics"], "Untranslated subject labels"
    save_json(ROOT / "课程完整数据.json", rows)
    table = [table_row(r) for r in rows]
    with (ROOT / "课程总目录.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        for row in table:
            # Avoid formula execution when public source strings are opened in Excel.
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(("=","+","-","@")) else v) for k,v in row.items()})
    save_json(ROOT / "workbook_rows.json", {"headers": list(table[0]), "rows": [list(r.values()) for r in table]})
    template = (ROOT / "catalogue_template.html").read_text(encoding="utf-8")
    data = json.dumps({"courses": rows, "audit": audit, "rules": CATEGORY_RULES}, ensure_ascii=False).replace("<", "\\u003c")
    (ROOT / "打开课程目录.html").write_text(template.replace("__CATALOGUE_DATA__", data), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print(f"Outputs saved in {ROOT}")


if __name__ == "__main__":
    main()
