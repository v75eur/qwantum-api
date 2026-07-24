from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests, os, dns.resolver, csv, time, random, threading, re, smtplib, base64
from datetime import datetime

app = Flask(__name__)
CORS(app)

GH_TOKEN = os.environ.get('GH_TOKEN','')
YT_KEY = os.environ.get('YT_KEY','')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

LOGS = {"np": [], "gt": [], "y@": []}
LOCKS = {"np": threading.Lock(), "gt": threading.Lock(), "y@": threading.Lock()}

def log(m, msg):
    t = datetime.now().strftime('%H:%M:%S')
    line = f"[{t}] {msg}"
    print(f"[{m}] {line}", flush=True)
    with LOCKS[m]: LOGS[m].append(line); del LOGS[m][:-500]

# 3 fichiers par moteur
FILES = {
    "np": {"L3": "L3_np.csv", "L4": "L4_np.csv", "L5": "L5_np.csv"},
    "gt": {"L3": "L3_gt.csv", "L4": "L4_gt.csv", "L5": "L5_gt.csv"},
    "y@": {"L3": "L3_y@.csv", "L4": "L4_y@.csv", "L5": "L5_y@.csv"}
}

DISPOSABLE = {'mailinator.com','tempmail.com','10minutemail.com','guerrillamail.com','yopmail.com','throwaway.email','trashmail.com','sharklasers.com','temp-mail.org','fakeinbox.com','maildrop.cc','getnada.com','mailnesia.com','spamgourmet.com'}

def count_csv(f):
    try:
        with open(f) as fh: return len(fh.readlines())-1
    except: return 0

def read_csv(f):
    e=[]
    try:
        with open(f) as fh:
            for l in fh.readlines()[1:]:
                if l.strip(): e.append(l.strip())
    except: pass
    return e

def save_csv(f, emails):
    with open(f, 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['email'])
        for e in sorted(emails): w.writerow([e])

def dns_ok(email):
    try: dns.resolver.resolve(email.split('@')[1],'MX'); return True
    except: return False

def is_disposable(email):
    return email.split('@')[1].lower() in DISPOSABLE

def is_catch_all(domain, td):
    if domain in td: return td[domain]
    try:
        rnd = f"test{int(time.time())}@{domain}"
        mx = str(dns.resolver.resolve(domain,'MX')[0].exchange)
        s = smtplib.SMTP(mx, 25, timeout=8)
        s.helo(); s.mail('check@system.net')
        code, _ = s.rcpt(rnd); s.quit()
        td[domain] = (code == 250)
        return td[domain]
    except:
        td[domain] = False
        return False

def verify(email, td):
    """Retourne 'L3', 'L4', ou None"""
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email): return None
    if is_disposable(email): return None
    if not dns_ok(email): return None
    domain = email.split('@')[1]
    if is_catch_all(domain, td): return 'L3'
    return 'L4'

def scrape_npm(kw):
    found=[]
    try:
        r=requests.get(f"https://registry.npmjs.org/-/v1/search?text={kw}&size=50",timeout=10)
        if r.status_code==200:
            for obj in r.json().get("objects",[]):
                for m in obj.get("package",{}).get("maintainers",[]):
                    mail=m.get("email","")
                    if EMAIL_REGEX.search(mail):
                        em=mail.lower()
                        if em not in found: found.append(em)
    except: pass
    return found

def scrape_github(kw):
    found=[]
    if not GH_TOKEN: return found
    h={"Authorization":f"token {GH_TOKEN}"}
    try:
        r=requests.get(f"https://api.github.com/search/code?q={kw}+@gmail.com&per_page=20",headers=h,timeout=10)
        if r.status_code==200:
            for item in r.json().get("items",[]):
                repo=item.get("repository",{}).get("full_name","")
                path=item.get("path","")
                for br in['main','master']:
                    try:
                        r2=requests.get(f"https://raw.githubusercontent.com/{repo}/{br}/{path}",timeout=5)
                        if r2.status_code==200:
                            for e in EMAIL_REGEX.findall(r2.text):
                                em=e.lower()
                                if em not in found: found.append(em)
                    except: pass
    except: pass
    return found

def scrape_youtube(kw):
    found=[]
    if not YT_KEY: return found
    try:
        r=requests.get("https://www.googleapis.com/youtube/v3/search",
            params={"key":YT_KEY,"q":kw,"type":"channel","maxResults":30,"part":"snippet"},timeout=10)
        if r.status_code==200:
            for item in r.json().get("items",[]):
                cid=item['snippet']['channelId']
                try:
                    r2=requests.get("https://www.googleapis.com/youtube/v3/channels",
                        params={"key":YT_KEY,"id":cid,"part":"brandingSettings,snippet"},timeout=10)
                    if r2.status_code==200:
                        items=r2.json().get("items",[])
                        if items:
                            desc=items[0].get("snippet",{}).get("description","")
                            for e in EMAIL_REGEX.findall(desc):
                                em=e.lower()
                                if em not in found: found.append(em)
                except: pass
    except: pass
    return found

def push_to_github(filename, content):
    if not GH_TOKEN: return
    try:
        encoded=base64.b64encode(content.encode()).decode()
        url=f"https://api.github.com/repos/v75eur/qwantum-api/contents/{filename}"
        r=requests.get(url,headers={"Authorization":f"token {GH_TOKEN}"})
        sha=r.json().get('sha','') if r.status_code==200 else ''
        data={"message":"Auto L4","content":encoded}
        if sha: data["sha"]=sha
        requests.put(url,headers={"Authorization":f"token {GH_TOKEN}"},json=data)
    except: pass

def run_moteur(m, scraper):
    WORDS=['trading','forex','crypto','investing','stocks','bitcoin','ethereum','finance','business','marketing','startup','python','javascript','react','node','developer','blockchain','defi','nft','ai','machine','data','cloud','docker','aws']
    L3=set(read_csv(FILES[m]["L3"])); L4=set(read_csv(FILES[m]["L4"])); L5=set(read_csv(FILES[m]["L5"]))
    SEEN=L3|L4|L5
    tested={}
    log(m, f"🚀 L3:{len(L3)} | L4:{len(L4)} | L5:{len(L5)}")
    while True:
        kw=random.choice(WORDS)
        log(m, f"🔍 {kw}")
        new=scraper(kw)
        added_L3=0; added_L4=0
        for em in new:
            if em in SEEN: continue
            SEEN.add(em)
            level=verify(em, tested)
            if level=='L4': L4.add(em); added_L4+=1; log(m, f"✅ L4: {em}")
            elif level=='L3': L3.add(em); added_L3+=1; log(m, f"⚠️ L3: {em}")
        if added_L3: save_csv(FILES[m]["L3"], L3)
        if added_L4:
            save_csv(FILES[m]["L4"], L4)
            # Push L4 vers GitHub pour vérification SMTP
            push_to_github(FILES[m]["L4"], '\n'.join(['email']+sorted(L4)))
        if added_L3 or added_L4:
            log(m, f"📊 +{added_L3+added_L4} | L3:{len(L3)} | L4:{len(L4)} | L5:{len(L5)}")
        time.sleep(random.randint(10,30))

threading.Thread(target=run_moteur,args=("np",scrape_npm),daemon=True).start()
threading.Thread(target=run_moteur,args=("gt",scrape_github),daemon=True).start()
threading.Thread(target=run_moteur,args=("y@",scrape_youtube),daemon=True).start()

@app.route('/stats/<m>')
def stats(m):
    if m not in FILES: return jsonify({})
    return jsonify({"L3":count_csv(FILES[m]["L3"]),"L4":count_csv(FILES[m]["L4"]),"L5":count_csv(FILES[m]["L5"])})

@app.route('/live/<m>')
def live(m):
    if m not in LOGS: return Response("",mimetype='text/event-stream')
    def g():
        last=0
        while True:
            with LOCKS[m]: l=len(LOGS[m])
            if l>last:
                with LOCKS[m]:
                    for i in range(last,l): yield f"data: {LOGS[m][i]}\n\n"
                last=l
            time.sleep(0.3)
    return Response(g(),mimetype='text/event-stream')

@app.route('/download/<m>/<t>')
def download(m,t):
    if m not in FILES: return jsonify({"emails":[]})
    t = f"L{t}" if t in ['3','4','5'] else t
    if t not in FILES[m]: return jsonify({"emails":[]})
    n=request.args.get('n',50,type=int)
    return jsonify({"emails":read_csv(FILES[m][t])[:n]})

@app.route('/clear/<m>')
def clear(m):
    if m not in FILES: return jsonify({"msg":"?"})
    for t in FILES[m].values(): save_csv(t, [])
    return jsonify({"msg":f"{m} vidé"})

@app.route('/')
def home(): return "OK"

if __name__=='__main__': app.run(host='0.0.0.0',port=10000,threaded=True)
