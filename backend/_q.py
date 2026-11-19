import sqlite3

c = sqlite3.connect('data/videomind.db')
cur = c.cursor()


def dump(sql, title):
    print('--- ' + title + ' ---')
    try:
        for r in cur.execute(sql):
            print(r)
    except Exception as e:
        print('ERR', e)


dump('select schema_type,count(*) from artifact group by schema_type', 'artifact schema_type')
dump('select type,count(*) from knowledge_item group by type', 'item type')
dump('select confidence,count(*) from knowledge_item group by confidence', 'item confidence')
dump('select state,count(*) from revision group by state', 'revision state')
dump('select channel,count(*) from evidence group by channel', 'evidence channel')
dump("select case when frame_path='' then 'empty' else 'has' end as k,count(*) from evidence group by k", 'evidence frame_path')
dump('select id,name,suggested_by_ai from tag', 'tag')
dump('select target_type,count(*) from tag_binding group by target_type', 'tag_binding target')
dump('select id,item_id,source_a,source_b,substr(description,1,80) from conflict_record', 'conflict')
dump('select id,transcribe_status,visual_status,structure_status,artifact_status from video', 'stage matrix')
dump('select video_id,evidence_id,count(*) from knowledge_item group by 1,2 order by 1', 'item evidence ids')
dump("select count(*) from knowledge_item where evidence_id is null", 'items without evidence')
