import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
con = sqlite3.connect('BE/smartbuddy.db')
cur = con.cursor()
for r in cur.execute('select id,user_id,subject,topic,score,total,created_at from score_records order by created_at desc'):
    print(r)
