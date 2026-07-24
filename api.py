from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests, os, dns.resolver, csv, time, random, threading, re, smtplib
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
    "np": {"dns": "dns_np.csv", "smtp": "smtp_np.csv", "final": "final_np.csv"},
    "gt": {"dns": "dns_gt.csv", "smtp": "smtp_gt.csv", "final": "final_gt.csv"},
    "y@": {"dns": "dns_y@.csv", "smtp": "smtp_y@.csv", "final": "final_y@.csv"}
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
    """Retourne le niveau: 'dns', 'smtp', ou None"""
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return None
    if is_disposable(email):
        return None
    if not dns_ok(email):
        return None
    domain = email.split('@')[1]
    if is_catch_all(domain, td):
        return 'dns'  # 3/5, catch-all détecté
    return 'smtp'  # 4/5, prêt pour SMTP final

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

def run_moteur(m, scraper):
    WORDS=['trading','forex','crypto','investing','stocks','bitcoin','ethereum','finance','business','marketing','startup','python','javascript','react','node','developer','blockchain','defi','nft','ai','machine','data','cloud','docker','aws']
    SEEN=set(read_csv(FILES[m]["dns"]) + read_csv(FILES[m]["smtp"]) + read_csv(FILES[m]["final"]))
    dns_set=set(read_csv(FILES[m]["dns"]))
    smtp_set=set(read_csv(FILES[m]["smtp"]))
    final_set=set(read_csv(FILES[m]["final"]))
    tested={}
    log(m, f"🚀 DNS:{len(dns_set)} | SMTP:{len(smtp_set)} | FINAL:{len(final_set)}")
    while True:
        kw=random.choice(WORDS)
        log(m, f"🔍 {kw}")
        new=scraper(kw)
        dns_added=0; smtp_added=0
        for em in new:
            if em in SEEN: continue
            SEEN.add(em)
            level=verify(em, tested)
            if level=='smtp':
                smtp_set.add(em); smtp_added+=1
                log(m, f"✅ SMTP: {em}")
            elif level=='dns':
                dns_set.add(em); dns_added+=1
                log(m, f"⚠️ DNS: {em}")
        if dns_added: save_csv(FILES[m]["dns"], dns_set)
        if smtp_added: save_csv(FILES[m]["smtp"], smtp_set)
        if dns_added or smtp_added:
            log(m, f"📊 +{dns_added+smtp_added} | DNS:{len(dns_set)} | SMTP:{len(smtp_set)} | FINAL:{len(final_set)}")
        time.sleep(random.randint(10,30))

threading.Thread(target=run_moteur,args=("np",scrape_npm),daemon=True).start()
threading.Thread(target=run_moteur,args=("gt",scrape_github),daemon=True).start()
threading.Thread(target=run_moteur,args=("y@",scrape_youtube),daemon=True).start()

@app.route('/stats/<m>')
def stats(m):
    if m not in FILES: return jsonify({})
    return jsonify({
        "dns": count_csv(FILES[m]["dns"]),
        "smtp": count_csv(FILES[m]["smtp"]),
        "final": count_csv(FILES[m]["final"])
    })

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
    if m not in FILES or t not in FILES[m]: return jsonify({"emails":[]})
    n=request.args.get('n',50,type=int)
    return jsonify({"emails":read_csv(FILES[m][t])[:n]})

@app.route('/clear/<m>/<t>')
def clear(m,t):
    if m not in FILES or t not in FILES[m]: return jsonify({"msg":"?"})
    save_csv(FILES[m][t], [])
    return jsonify({"msg":f"{m}/{t} vidé"})

@app.route('/')
def home(): return "OK"

if __name__=='__main__': app.run(host='0.0.0.0',port=10000,threaded=True)
