from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests, os, dns.resolver, csv, time, random, threading, re
from datetime import datetime

app = Flask(__name__)
CORS(app)

KEYS = os.environ.get('GROQ_KEYS','').split(',') or ['demo']
SITE_PASSWORD = os.environ.get('SITE_PASSWORD', 'RickRoss1994@')
EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
LIVE_LOGS = []
LOG_LOCK = threading.Lock()

def log(msg):
    t = datetime.now().strftime('%H:%M:%S')
    line = f"[{t}] {msg}"
    print(line, flush=True)
    with LOG_LOCK:
        LIVE_LOGS.append(line)
        if len(LIVE_LOGS) > 500: LIVE_LOGS.pop(0)

BANQUE_URL = 'https://raw.githubusercontent.com/v75eur/qwantum/main/banque_verified.csv'

def fetch_emails():
    e = []
    try:
        r = requests.get(BANQUE_URL, timeout=10)
        if r.status_code == 200:
            for l in r.text.strip().split('\n')[1:]:
                if l.strip(): e.append(l.strip())
    except: pass
    return e

def dns_ok(email):
    try: dns.resolver.resolve(email.split('@')[1], 'MX'); return True
    except: return False

def scrape_npm(kw):
    found = []
    try:
        r = requests.get(f"https://registry.npmjs.org/-/v1/search?text={kw}&size=50", timeout=10)
        if r.status_code == 200:
            for obj in r.json().get("objects",[]):
                for m in obj.get("package",{}).get("maintainers",[]):
                    mail = m.get("email","")
                    if EMAIL_REGEX.search(mail):
                        em = mail.lower()
                        if em not in found:
                            if dns_ok(em):
                                found.append(em)
                                log(f"✅ DNS OK: {em}")
                            else:
                                log(f"❌ DNS KO: {em}")
    except Exception as e: log(f"❌ npm: {e}")
    return found

def scrape_github(kw):
    found = []
    tok = os.environ.get('GH_TOKEN','')
    if not tok: return found
    h = {"Authorization": f"token {tok}"}
    try:
        r = requests.get(f"https://api.github.com/search/code?q={kw}+@gmail.com&per_page=20", headers=h, timeout=10)
        if r.status_code == 200:
            for item in r.json().get("items",[]):
                repo = item.get("repository",{}).get("full_name","")
                path = item.get("path","")
                for br in ['main','master']:
                    try:
                        r2 = requests.get(f"https://raw.githubusercontent.com/{repo}/{br}/{path}", timeout=5)
                        if r2.status_code == 200:
                            for e in EMAIL_REGEX.findall(r2.text):
                                em = e.lower()
                                if em not in found:
                                    if dns_ok(em):
                                        found.append(em)
                                        log(f"✅ DNS OK: {em}")
                                    else:
                                        log(f"❌ DNS KO: {em}")
                    except: pass
    except Exception as e: log(f"❌ GH: {e}")
    return found

# --- SCRAPER CONTINU 6h-00h ---
def scraper_loop():
    WORDS = ['trading','forex','crypto','investing','stocks','bitcoin','ethereum','finance','business','marketing','startup','python','javascript','react','node','developer','blockchain','defi','nft','ai','machine','data','cloud','docker','aws']
    SEEN = set()
    BANQUE_FILE = 'banque_emails.csv'
    if os.path.exists(BANQUE_FILE):
        with open(BANQUE_FILE) as f:
            for l in f.readlines()[1:]:
                if l.strip(): SEEN.add(l.strip())
    log(f"🚀 SCRAPER DÉMARRÉ (6h-00h) | Brute: {len(SEEN)} | Vérifiée: {len(fetch_emails())}")
    while True:
        h = datetime.now().hour
        if 6 <= h < 24:
            kw = random.choice(WORDS)
            log(f"🔍 Recherche: '{kw}'")
            new = scrape_npm(kw) + scrape_github(kw)
            added = 0
            for em in new:
                if em not in SEEN:
                    SEEN.add(em)
                    added += 1
            if added:
                with open(BANQUE_FILE, 'w', newline='') as f:
                    w = csv.writer(f); w.writerow(['email'])
                    for e in sorted(SEEN): w.writerow([e])
                verif = len(fetch_emails())
                log(f"📊 +{added} nouveaux | Brute: {len(SEEN)} | Vérifiée: {verif} | ⏳ En attente SMTP")
            else:
                log(f"⏳ 0 nouveau avec '{kw}' | Brute: {len(SEEN)} | Vérifiée: {len(fetch_emails())}")
            time.sleep(random.randint(10, 30))
        else:
            log(f"💤 Nuit (00h-6h) | Brute: {len(SEEN)} | Vérifiée: {len(fetch_emails())}")
            time.sleep(60)

threading.Thread(target=scraper_loop, daemon=True).start()

# --- ROUTES ---
@app.route('/')
def home(): return "QWANTUM API OK"

@app.route('/count')
def count(): return jsonify({"count": len(fetch_emails())})

@app.route('/count-brute')
def count_brute():
    try:
        with open('banque_emails.csv') as f: return jsonify({"count": len(f.readlines())-1})
    except: return jsonify({"count": 0})

@app.route('/live-logs')
def live_logs():
    def generate():
        last_idx = 0
        while True:
            with LOG_LOCK:
                if len(LIVE_LOGS) > last_idx:
                    for i in range(last_idx, len(LIVE_LOGS)):
                        yield f"data: {LIVE_LOGS[i]}\n\n"
                    last_idx = len(LIVE_LOGS)
            time.sleep(0.3)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/chat', methods=['POST'])
def chat():
    global request_count, current_key
    d = request.get_json()
    if not d: return jsonify({"reply":"?"})
    if request_count >= 25: current_key = (current_key + 1) % len(KEYS); request_count = 0
    request_count += 1
    try:
        r = requests.post('https://api.groq.com/openai/v1/chat/completions',
            headers={'Content-Type':'application/json','Authorization':f'Bearer {KEYS[current_key]}'},
            json={'model':'llama-3.1-8b-instant','messages':[
                {'role':'system','content':'Tu es QWANTUM.'},
                {'role':'user','content':d['message']}
            ],'temperature':0.8,'max_tokens':200}, timeout=15)
        return jsonify({"reply": r.json()['choices'][0]['message']['content']})
    except: return jsonify({"reply": "Désolé."})

if __name__ == '__main__': app.run(host='0.0.0.0', port=10000, threaded=True)
