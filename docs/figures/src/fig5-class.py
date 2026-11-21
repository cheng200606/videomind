from pathlib import Path
from html import escape

W, H = 1800, 1240
FONT = "Source Han Sans CN, Microsoft YaHei, PingFang SC, Noto Sans CJK SC, sans-serif"
out = []
def add(s): out.append(s)
def text(x,y,s,size=12,weight="normal",fill="#0F172A",anchor="start"):
    add(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')
def rect(x,y,w,h,fill,stroke,rx=0,sw=1):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
def line(pts, stroke="#64748B", sw=1.1, dash=None, marker_end=None, marker_start=None):
    d=' stroke-dasharray="5 4"' if dash else ''
    me=f' marker-end="url(#{marker_end})"' if marker_end else ''
    ms=f' marker-start="url(#{marker_start})"' if marker_start else ''
    p=" ".join(f"{x},{y}" for x,y in pts)
    add(f'<polyline points="{p}" fill="none" stroke="{stroke}" stroke-width="{sw}"{d}{me}{ms} stroke-linejoin="round"/>')
def label(x,y,s,size=10,fill="#475569",anchor="middle"):
    add(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" stroke="#FFFFFF" stroke-width="3.2" paint-order="stroke" stroke-linejoin="round">{escape(s)}</text>')
def panel(x,y,w,h,title):
    rect(x,y,w,h,"#F8FAFC","#E2E8F0",8,1)
    text(x+16,y+24,title,13,"bold","#475569")
def box(x,y,w,title,fields,kind="class",stereo=None):
    hf = "#F5F3FF" if kind=="interface" else "#EEF2FF"
    st = "#7C3AED" if kind=="interface" else "#4338CA"
    header_h = 44 if stereo else 34
    h = header_h + 8 + len(fields)*17 + 10
    rect(x,y,w,h,"#FFFFFF",st,6,1.2)
    add(f'<path d="M{x+6},{y} h{w-12} a6,6 0 0 1 6,6 v{header_h-6} h-{w} v-{header_h-6} a6,6 0 0 1 6,-6 z" fill="{hf}"/>')
    add(f'<line x1="{x}" y1="{y+header_h}" x2="{x+w}" y2="{y+header_h}" stroke="{st}" stroke-width="1"/>')
    if stereo:
        text(x+w/2,y+15,stereo,10,"normal","#6D28D9","middle")
        text(x+w/2,y+34,title,14,"bold","#0F172A","middle")
    else:
        text(x+w/2,y+22,title,14,"bold","#0F172A","middle")
    for i,f in enumerate(fields):
        text(x+10,y+header_h+22+i*17,f,11.2,"normal","#334155")
    return h

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">')
add('''<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="#64748B" stroke-width="1.2"/></marker>
<marker id="tri" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse"><path d="M1,1 L11,6 L1,11 z" fill="#FFFFFF" stroke="#7C3AED" stroke-width="1.1"/></marker>
<marker id="diamond" viewBox="0 0 12 12" refX="1" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1,6 L6,1 L11,6 L6,11 z" fill="#4338CA" stroke="#4338CA" stroke-width="1"/></marker>
</defs>''')
rect(0,0,W,H,"#FFFFFF","#FFFFFF")

# services band
panel(20,30,1760,280,"解析与交付服务")
box(40,75,300,"pipeline.py",["+parse_video(session, video, settings=None) : Video","+parse_batch(session, batch)","+retry_video(session, video_id) : Video","+recover_orphan_runs(session)"],"class","«module»")
box(370,75,280,"ProgressBus",["+subscribe(batch_id)","+unsubscribe(q)","+reset(batch_id)","+forget(batch_id)","+emit(batch_id, video_id, stage, status, message)"])
box(680,75,200,"ParseMutex",["+claim(batch_id) : bool","+release(batch_id)"])
box(910,75,270,"llm.py",["+structure(transcript, ocr_text, duration_ms)","+report / progress 可选","+test_connection(cfg=None) : tuple"],"class","«module»")
box(1210,75,270,"export.py",["+build_batch_markdown(session, batch_id) : str","+coverage_notices(session, video, items) : str[]"],"class","«module»")
box(910,210,270,"StructuredDraft",["+chapters : Chapter[]","+items : DraftItem[]"])

# domain panel: 4 columns
panel(20,330,1120,890,"核心领域（11 个实体全画；完整字段见图 6）")
box(40,380,250,"VideoBatch",["+id : int","+name : str","+status : BatchStatus"])
box(40,500,250,"Video",["+id : int","+batchId : int","+durationMs : int","+status : VideoStatus"])
box(40,640,250,"Segment",["+id : int","+videoId : int","+startMs : int","+endMs : int"])
box(40,780,250,"Evidence",["+id : int","+videoId : int","+startMs : int","+quote : str","+channel : Channel"])
box(320,380,270,"KnowledgeItem",["+id : int","+videoId : int","+type : ArtifactType","+confidence : Confidence","+evidenceId : int"])
box(640,380,250,"Artifact",["+id : int","+itemId : int","+schemaType : ArtifactType"])
box(640,500,250,"ConflictRecord",["+id : int","+itemId : int","+description : str"])
box(640,640,250,"Note",["+id : int","+itemId : int","+anchorMs : int"])
box(640,760,250,"Revision",["+id : int","+itemId : int","+state : RevisionState"])
box(930,380,190,"Tag",["+id : int","+name : str"])
box(930,490,190,"TagBinding",["+id : int","+tagId : int","+targetType : TagTarget","+targetId : int"])
text(930,620,"targetType=video|item",10,"normal","#64748B")
text(930,638,"多态绑定，不设外键",10,"normal","#64748B")
text(40,980,"VideoBatch → Video → Segment/Evidence/KnowledgeItem 是 1:N 主链；",10.5,"normal","#64748B")
text(40,1000,"KnowledgeItem → Artifact/ConflictRecord/Note/Revision 是 1:N。",10.5,"normal","#64748B")
text(40,1020,"TagBinding 通过 targetType=video|item 多态绑定，不设外键。",10.5,"normal","#64748B")
text(40,1040,"主链基数：VideoBatch 1—0..* Video；Video 1—0..* Segment/Evidence/KnowledgeItem；",10.5,"normal","#64748B")
text(40,1060,"KnowledgeItem 1—0..* Artifact/ConflictRecord/Note/Revision；Tag 1—0..* TagBinding。",10.5,"normal","#64748B")

# strategy panel
panel(1160,330,620,890,"可插拔策略（三类 + 转写接缝）")
box(1180,380,240,"OcrEngine",["+name : str","+recognize(frames) : FrameText[]"],"interface","«interface»  «策略»")
box(1440,380,130,"RapidOcr",[])
box(1440,430,130,"PaddleOcr",[])
box(1440,480,130,"VisionModelOcr",[])
box(1180,550,250,"OutputSchemaStrategy",["+atype : ArtifactType","+payloadModel : type","+build(ctx) : ItemDraft[]"],"interface","«interface»  «策略»")
box(1450,550,140,"SummaryStrategy",[])
box(1450,600,140,"UmlDraftStrategy",[])
box(1450,650,140,"KeyPointsStrategy",[])
box(1450,700,140,"CodeBlocksStrategy",[])
box(1180,760,250,"AsrVocabularyCrossChecker",["+crossCheck(asr, ocr) : Correction[]"],"interface","«interface»  «策略 · 仅设计»")
box(1180,900,250,"AsrEngine",["+name : str","+isAvailable() : bool","+transcribe(path) : AsrResult"],"interface","«interface»  转写接缝")
box(1450,900,150,"实现",["MockAsr / WhisperAsr","YueyingAsr / FunASR"])

# service edges
line([(340,120),(370,120)])
line([(210,205),(210,305),(780,305),(780,161)], marker_end="arrow")
label(500,297,"进度 / 互斥")
line([(250,75),(250,58),(1045,58),(1045,75)], marker_end="arrow")
label(600,52,"结构化")
line([(190,205),(190,312),(460,312),(460,380)], marker_end="arrow")
label(300,304,"落库")
line([(1045,188),(1045,210)], marker_end="arrow")

# service -> strategy
line([(340,170),(360,170),(360,319),(1130,319),(1130,430),(1180,430)], marker_end="arrow")
label(700,311,"画面")
line([(350,190),(365,190),(365,326),(1140,326),(1140,605),(1180,605)], marker_end="arrow")
label(1000,318,"产物")
line([(350,200),(355,200),(355,333),(1150,333),(1150,950),(1180,950)], marker_end="arrow")
label(1000,325,"转写")

# domain edges: short, from KnowledgeItem right to child column
line([(165,480),(165,500)], marker_start="diamond")
line([(165,620),(165,640)], marker_start="diamond")
line([(290,560),(305,560),(305,855),(290,855)], marker_end="arrow")
line([(290,530),(320,530)], marker_start="diamond", marker_end="arrow")
line([(320,500),(310,500),(310,820),(290,820)], marker_end="arrow")
line([(600,430),(640,430)], marker_start="diamond", marker_end="arrow")
line([(600,500),(640,500)], marker_start="diamond", marker_end="arrow")
line([(600,530),(620,530),(620,690),(640,690)], marker_start="diamond", marker_end="arrow")
line([(600,510),(630,510),(630,820),(640,820)], marker_start="diamond", marker_end="arrow")
line([(1020,466),(1020,490)], marker_start="diamond")

# realizations
line([(1440,402),(1420,410)], dash="5 4", marker_end="tri")
line([(1440,452),(1420,440)], dash="5 4", marker_end="tri")
line([(1440,502),(1420,470)], dash="5 4", marker_end="tri")
line([(1450,571),(1430,580)], dash="5 4", marker_end="tri")
line([(1450,621),(1430,600)], dash="5 4", marker_end="tri")
line([(1450,671),(1430,620)], dash="5 4", marker_end="tri")
line([(1450,721),(1430,640)], dash="5 4", marker_end="tri")

# F5: left margin to OcrEngine; vertical to AsrEngine
line([(1180,780),(1170,780),(1170,430),(1180,430)], dash="5 4", marker_end="arrow")
label(1164,600,"读画面",anchor="end")
line([(1305,860),(1305,900)], dash="5 4", marker_end="arrow")
label(1312,878,"仅设计",anchor="start")

# notes/legend
text(1180,1060,"实线：关联 / 组合 / 调用；虚线：实现 / 设计级依赖；◆：组合；▷：实现。",10.5,"normal","#64748B")
text(1180,1080,"三类策略：OcrEngine（画面）、OutputSchemaStrategy（产物）、AsrVocabularyCrossChecker（F5，仅设计，本期不实现）。",10.5,"normal","#64748B")
text(20,1080,"DTO：AsrResult / TranscriptSegment / KeyFrame / FrameText / ParseContext / ItemDraft；StructuredDraft 另含 conflicts。",10.5,"normal","#64748B")
text(20,1120,"DTO 字段：AsrResult(duration_ms, segments, frames)；",10.5,"normal","#64748B")
text(20,1140,"ParseContext(draft, segments, frames, ocr, duration_ms, notices)；ItemDraft 见 artifacts.py:18。",10.5,"normal","#64748B")
text(20,1160,"AsrEngine 实现：MockAsr / WhisperAsr / YueyingAsr / FunASR；不计入三类策略。",10.5,"normal","#64748B")

add('</svg>')
Path("docs/figures/svg/fig5-class.svg").write_text("\n".join(out), encoding="utf-8")
print("wrote", len("\n".join(out)), "bytes")
