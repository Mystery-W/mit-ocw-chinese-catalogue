/** Export the bilingual catalogue as an Excel workbook with auditable full text.
 * The large directory remains filterable. Full descriptions are held separately,
 * split into numbered continuation rows when needed so text fits Excel row limits.
 * Uses only the bundled artifact-tool runtime; never installs or changes packages.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';

const root=path.dirname(fileURLToPath(import.meta.url));
const data=JSON.parse(await fs.readFile(path.join(root,'workbook_rows.json'),'utf8'));
const courses=JSON.parse(await fs.readFile(path.join(root,'课程完整数据.json'),'utf8'));
const audit=JSON.parse(await fs.readFile(path.join(root,'validation.json'),'utf8'));
const wb=Workbook.create();
const main=wb.worksheets.add('课程目录'), descriptions=wb.worksheets.add('课程简介'), guide=wb.worksheets.add('使用说明');
const font='Microsoft YaHei';
const outdir=path.join(root,'outputs','ocw_20261117');
await fs.mkdir(outdir,{recursive:true});

/** Style one bounded table, preserving identifiers as text and enabling filters. */
function styleTable(sheet,rows,columns,name){
  const range=sheet.getRangeByIndexes(5,0,rows,columns);
  range.format.font={name:font,size:10,color:'#20343C'};
  range.format.wrapText=true;range.format.verticalAlignment='top';
  range.format.rowHeight=90;range.format.columnWidth=28;
  const head=sheet.getRangeByIndexes(5,0,1,columns);
  head.format.fill='#23453F';head.format.font={name:font,size:10,bold:true,color:'#FFFFFF'};
  head.format.rowHeight=36;head.format.verticalAlignment='center';
  const table=sheet.tables.add(range,true,name);table.showFilterButton=true;
  sheet.showGridLines=false;sheet.freezePanes.freezeRows(6);sheet.freezePanes.freezeColumns(1);
  sheet.getRange('A2').format.font={name:font,size:16,bold:true,color:'#20343C'};
  sheet.getRange('A4').format.font={name:font,size:10,color:'#63746F'};
}

const headers=[...data.headers];headers[5]='课程介绍摘录（全文见课程简介）';
const matrix=[headers,...data.rows.map(row=>{const r=[...row];r[5]=String(r[5]).slice(0,200)+(String(r[5]).length>200?'…':'');return r;})];
main.getRangeByIndexes(5,0,matrix.length,headers.length).values=matrix;
styleTable(main,matrix.length,headers.length,'CourseCatalogue');
main.getRange('A2').values=[['MIT OCW 中文课程目录']];
main.getRange('A4').values=[['2026-11-17 快照。中文为 AI 辅助译名；同代码不同学期分别保留。完整简介见“课程简介”，以课程链接区分版本。']];
for(const [col,width] of [['A',16],['B',55],['C',38],['D',48],['E',28],['F',68],['G',65],['H',52],['I',52],['N',65],['P',65],['S',65],['T',75],['Y',40],['AA',70],['AC',32],['AD',65],['AE',65]])main.getRange(`${col}6:${col}${matrix.length+5}`).format.columnWidth=width;
main.getRange(`A7:A${matrix.length+5}`).setNumberFormat('@');
main.getRange(`V7:V${matrix.length+5}`).setNumberFormat('0');

/** Split long prose at whitespace, retaining every original character in order. */
function splitText(text,maxLength=1800){const parts=[];let remaining=text;while(remaining.length>maxLength){let cut=remaining.lastIndexOf(' ',maxLength);if(cut<maxLength/2)cut=maxLength;else cut++;parts.push(remaining.slice(0,cut));remaining=remaining.slice(cut);}parts.push(remaining);return parts;}
const fullRows=[['课程代码','课程标题（英文）','课程标题（中文辅助译名）','分段','课程介绍（官方英文全文，按分段顺序阅读）','课程链接']];
for(const c of courses){const parts=splitText(c.description_en);parts.forEach((text,i)=>fullRows.push([c.course_code,c.title_en,c.title_zh,`${i+1}/${parts.length}`,text,c.course_url]));}
descriptions.getRangeByIndexes(5,0,fullRows.length,6).values=fullRows;
styleTable(descriptions,fullRows.length,6,'CourseDescriptions');
descriptions.getRange('A2').values=[['课程介绍全文']];
descriptions.getRange('A4').values=[['每个课程版本按课程链接对应。长简介分段排列，分段拼接即为完整原文，没有摘要改写。']];
for(const [col,width] of [['A',16],['B',55],['C',38],['D',10],['E',150],['F',65]])descriptions.getRange(`${col}6:${col}${fullRows.length+5}`).format.columnWidth=width;
// Conservative line budget accommodates word wrapping and long English titles.
fullRows.slice(1).forEach((row,i)=>{const lines=Math.max(Math.ceil(row[4].length/135)+2,Math.ceil(row[1].length/50)+1,Math.ceil(row[2].length/18)+1);descriptions.getRangeByIndexes(i+6,0,1,6).format.rowHeight=Math.min(380,Math.max(65,lines*16));});

const notes=[
 ['范围与方法','结果或说明'],
 ['抓取日期','2026-11-17，UTC+08'],
 ['课程版本数',audit.course_count],
 ['不同课程代码',audit.unique_codes],
 ['首页与元数据抓取成功',audit.course_count-audit.failed_captures],
 ['目录覆盖核对','搜索接口与站点地图均为 2587 个课程版本，差集为空。'],
 ['包含的信息','课程代码、中英文标题、学科、学习资源类型、官方完整简介、院系、学期、教师、原始链接及抓取时间。'],
 ['中文标题','AI 辅助译名，非 MIT 官方译本；尚未经逐项专业审校。'],
 ['学习内容分类','按官方资源标签、课程导航及重点资源页核查分类；与本科/研究生等学术级别分开。'],
 ['视频限制','有视频证据不保证所有讲次齐全；未逐个验证视频播放、字幕或所在地区访问情况。'],
 ['外部平台','仅记录外部课程与 MOOC 入口，未逐项核验收费、报名、下载及播放。'],
 ['已退役课程','6.00 与 6.00SC 的对应旧版入口明确说明已退役，转向 DSpace 档案库。'],
 ['完整简介','“课程目录”显示摘录，完整官方英文简介在“课程简介”；长文按编号分段。CSV、JSON、HTML 保留整段全文。'],
 ['资源下载范围','保存课程级元数据、首页和核查证据。未批量下载视频、PDF、作业附件或字幕。'],
 ['离线浏览','双击“打开课程目录.html”。支持中文搜索、双学科交叉筛选、视频筛选、完整简介与筛选结果 CSV 导出。'],
 ['来源','https://ocw.mit.edu/search/'],
 ['站点地图','https://ocw.mit.edu/sitemap.xml'],
 ['许可','页面元数据标示 CC BY-NC-SA 4.0；外部网站及个别素材可能另有许可。'],
 ['官网归属','课程与简介来自 MIT OpenCourseWare；目录编排和中文辅助译名不代表 MIT 官方认可。'],
 ['', ''],['主要学习内容分类','课程版本数'],...Object.entries(audit.resource_counts)
];
guide.getRangeByIndexes(5,0,notes.length,2).values=notes;
styleTable(guide,notes.length,2,'CatalogueGuide');guide.freezePanes.unfreeze();
guide.getRange('A2').values=[['范围与使用说明']];guide.getRange(`A6:A${notes.length+5}`).format.columnWidth=30;
guide.getRange(`B6:B${notes.length+5}`).format.columnWidth=110;
guide.getRange(`A7:B${notes.length+5}`).format.rowHeight=48;
guide.getRange('A4').values=[['课程资源类型是导航信息，不是质量评分或课程难度排名。']];
main.tabColor='#23453F';guide.tabColor='#899A8F';
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'课程目录!A6:F9',include:'values',tableMaxRows:4,tableMaxCols:6,maxChars:2500})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:10},maxChars:800})).ndjson);
const exported=await SpreadsheetFile.exportXlsx(wb);
await exported.save(path.join(outdir,'MIT_OCW课程总目录.xlsx'));
// Render representative ranges on every sheet to check Chinese typography/layout.
for(const [sheet,range,name] of [['课程目录','A2:E9','catalogue_preview.png'],['课程简介','A6:E8','description_preview.png'],['使用说明','A2:B15','guide_preview.png']]){
  const preview=await wb.render({sheetName:sheet,range,scale:1,format:'png'});
  await fs.writeFile(path.join(root,name),new Uint8Array(await preview.arrayBuffer()));
}
console.log(JSON.stringify({output:path.join(outdir,'MIT_OCW课程总目录.xlsx'),courses:courses.length,descriptionRows:fullRows.length-1}));
