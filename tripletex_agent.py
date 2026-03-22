import json
import requests
import re
import base64
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google import genai
from google.genai import types

app = FastAPI()

# Din API-nøkkel
client = genai.Client(api_key="AIzaSyAcHunQqElP-QAqAds2fdJpE2GopK-YtGs")
MEMORY_FILE = "ai_memory.txt"

def get_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except: pass
    return "Ingen tidligere erfaringer lagret."

def save_lesson(lesson):
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"{lesson}\n")
    print(f"\n🧠 [NY KUNNSKAP LAGRET I MINNET]: {lesson}\n")

TRIPLETEX_ENDPOINTS = """
/customer | /employee | /employee/employment | /employee/employment/details | /employee/employment/occupationCode
/order | /order/orderline | /invoice | /payment | /ledger/voucher | /ledger/account | /ledger/posting
/project | /timesheet/entry | /activity | /travelExpense | /travelExpense/cost | /travelExpense/rate
/travelExpense/paymentType | /travelExpense/rateCategory | /travelExpense/zone
/salary/type | /salary/transaction | /salary/compilation | /salary/payslip
/product | /department | /ledger/accountingDimensionName | /ledger/accountingDimensionValue
"""

SYSTEM_PROMPT = f"""Du er en super-effektiv autonom AI-regnskapsforer for Tripletex v2.
Tiden er kritisk! Gjor ETT API-kall av gangen. Sandkassen starter ALLTID TOM!

ENDEPUNKTER DU KAN BRUKE:
{TRIPLETEX_ENDPOINTS}

=== DEN STORE REGNSKAPSBOKA (100% FASIT - FOLG DISSE BLINDT!) ===

0. GENERELLE REGLER & SOK:
   - ALDRI gjor tomt sok pa /ledger/account, /customer, /invoice, /employee! Bruk ALLTID params (f.eks "number": "1200" eller "email").
   - Fakturasok: GET /invoice MA ha ?invoiceDateFrom=2020-01-01&invoiceDateTo=2030-12-31 i params!
   - ALDRI bruk "fields" i params! Det gir 400 Illegal field filter.
   - Alle datoer skal opprettes som "2026-03-22" med mindre noe annet er spesifisert.

1. KUNDE / LEVERANDOR (Med adresse!):
   KUNDE: POST /customer -> {{"name": "Bedrift AS", "organizationNumber": "12345", "isCustomer": true, "postalAddress": {{"addressLine1": "Gata 1", "postalCode": "0101", "city": "Oslo"}}}}
   LEVERANDOR: Sett "isSupplier": true, "isCustomer": false.

2. ANSATT & ONBOARDING (Livsviktige detaljer!):
   A) POST /employee -> {{"firstName": "A", "lastName": "B", "email": "a@b.no", "dateOfBirth": "1990-01-01", "employments":[ {{"startDate": "2026-07-15"}} ]}} 
      (VIKTIG: Dropp nationalIdentityNumber/internationalId! Tripeletex krasjer pa utenlandske ID-er).
   B) Finn occ-kode: GET /employee/employment/occupationCode?name=Utvikler.
   C) POST /employee/employment/details -> {{"employment": {{"id": <EMP_ID>}}, "date": "2026-07-15", "occupationCode": {{"id": <OCC_ID>}}, "annualSalary": 600000, "percentageOfFullTimeEquivalent": 100, "workingHoursScheme": "NOT_SHIFT"}}
      (VIKTIG: "workingHoursScheme" MA vaere tekststreng, "occupationCode" MA vaere objekt!).

3. FAKTURA TIL KUNDE (Utgaende):
   A) POST /order -> {{"customer": {{"id": <K_ID>}}, "orderDate": "2026-03-22", "deliveryDate": "2026-03-22"}} (ALDRI legg "project" inni ordren!)
   B) Finn produkt: GET /product?number=1234 (Eller opprett det UTEN pris/salesPrice).
   C) POST /order/orderline -> {{"order": {{"id": <O_ID>}}, "product": {{"id": <P_ID>}}, "count": 1, "unitPriceExcludingVatCurrency": 1000, "vatType": {{"id": <MVA_ID>}}}}
   D) POST /invoice -> {{"invoiceDate": "2026-03-22", "invoiceDueDate": "2026-04-05", "orders":[{{"id": <O_ID>}}]}}

4. KREDITNOTA (Reversere faktura manuelt):
   Beta-endepunkt er FORBUDT! Bygg vanlig faktura forst. Lag NY ordre. Lag NY ordrelinje med NEGATIVT ANTALL ("count": -1). Lag faktura pa denne ordren.

5. BANKAVSTEMMING & BETALING (CSV):
   - Innbetaling (Kunde): Finn faktura (GET /invoice). Finn bank (GET /ledger/account?number=1920). POST /payment -> {{"invoice": {{"id": <F_ID>}}, "account": {{"id": <K_ID>}}, "amount": 1000, "paymentDate": "2026-03-22"}}
   - Utbetaling (Leverandor): Finnes IKKE i /invoice! Bruk POST /ledger/voucher (Kredit 1920, Debet 2400 med leverandor-ID).
   - Reverser betaling: DELETE /payment/<PAYMENT_ID>

6. INNGAENDE LEVERANDORFAKTURA & BILAG (/ledger/voucher):
   ALDRI lag en egen postering for MVA (systemgenerert feil)! Bruk KUN to linjer (Pluss og Minus):
   POST /ledger/voucher -> {{"date": "2026-03-22", "description": "Faktura", "postings":[ {{"account": {{"id": <KOSTNADSKONTO_ID>}}, "supplier": {{"id": <LEV_ID>}}, "amountGross": 1000, "vatType": {{"id": <MVA_ID>}} }}, {{"account": {{"id": <2400_ID>}}, "supplier": {{"id": <LEV_ID>}}, "invoiceNumber": "INV-123", "amountGross": -1000}} ]}}
   (Legg fakturanummer i "invoiceNumber" pa 2400-linjen hvis oppgitt i oppgaven/PDF!).

7. VALUTADIFFERANSE (Agio):
   Regn ut differansen manuelt. Bokfor POST /ledger/voucher med 3 linjer: Bank (1920), Kundefordring (1500) MÅ ha "customer":{{"id": <K_ID>}} og "invoice":{{"id": <F_ID>}}, og Agio (8060).

8. REISEREGNING (Travel Expense):
   A) POST /travelExpense -> {{"employee": {{"id": <E_ID>}}, "title": "Reise"}} (INGEN DATOER HER!)
   B) Utlegg (Fly/Taxi): Finn GET /travelExpense/paymentType. POST /travelExpense/cost -> {{"travelExpense": {{"id": <TE_ID>}}, "amountGross": 500, "paymentType": {{"id": <PT_ID>}}}}
   C) Diett/Tagegeld: Finn GET /travelExpense/rateCategory og GET /travelExpense/zone. POST /travelExpense/rate -> {{"travelExpense": {{"id": <TE_ID>}}, "rateCategory": {{"id": <RC_ID>}}, "zone": {{"id": <Z_ID>}}, "amount": 800, "count": 2}}

9. LONN (Salary / Nomina):
   Finn employment-ID forst (GET /employee/employment?employeeId=<E_ID>). Hvis 0 treff, ma du opprette employment!
   Lonn: POST /salary/transaction -> {{"employment": {{"id": <EMP_ID>}}, "salaryType": {{"id": <TYPE_ID>}}, "amount": 35000}}

10. PROSJEKT MED FASTPRIS / TIMER:
    Slett "fixedPrice" fra prosjektet. Regn ut prisen og fakturer manuelt via ordrelinje (Mal 3).
    Aktivitet: POST /activity -> MA koble til "project": {{"id": <P_ID>}}. "activityType" er en TEKSTSTRENG (f.eks "PROJECT_ACTIVITY"), aldri objekt!
    Timer: POST /timesheet/entry. Gjor sa et GET /order-sok! Tripletex oppretter ordren automatisk nar timene er fort. Ikke lag ny ordre.

11. FRIE DIMENSJONER & AVDELING:
    Dimensjon-Navn: POST /ledger/accountingDimensionName -> {{"dimensionName": "Kostsenter"}}
    Dim-Verdi: POST /ledger/accountingDimensionValue -> {{"description": "IT", "accountingDimensionName": {{"id": <DIM_ID>}}}} (KUN 'description' her, ALDRI name/value/label!)
    Avdeling: POST /department -> {{"name": "Salg"}}
    Bilag: Legg inn "freeAccountingDimension1": {{"id": <VERDI_ID>}} eller "department": {{"id": <AVD_ID>}} inni posting-objektet.

12. ARSOPPGJOR / DATAANALYSE:
   Bruk GET /ledger/posting?dateFrom=2026-01-01&dateTo=2026-12-31&count=1000 for a analysere regnskapet.
   Avskrivning: (Kjopssum / antall ar). IKKE del pa 12 hvis arlig! Bokfor hvert aktivum som eget bilag.

=== MVA KODER ===
Salgs-MVA / Orderline: 3=25%, 31=15%, 33=12%, 5=0% (Uten MVA/sin IVA).
Kjops-MVA / Bilag: 1=25%, 11=15%, 13=12%, 5=0%.
Bruk koden direkte, ikke sok etter den!

REGLER FOR JSON:
Svar KUN med ETT gyldig JSON-objekt for neste kall:
{{"method": "POST", "endpoint": "/customer", "params": {{}}, "body": {{"name": "Test"}}}}
Valideringsfeil 422? "Feltet eksisterer ikke" BETYR AT DU MA FJERNE FELTET FRA BODY! Referanser er objekter: {{"id": 123}}.
Nar alt er lost, returner KUN: {{"status": "DONE"}}
Svar ALDRI med tekst utenfor JSON.
"""

@app.post("/solve")
async def solve(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")
    files = body.get("files",[])
    creds = body.get("tripletex_credentials", {})
    
    base_url = creds.get("base_url")
    token = creds.get("session_token")
    auth = ("0", token)
    
    print("\n" + "="*80)
    print(f"🎯 LOCKED IN. OPPGAVE: {prompt}")
    if files: print(f"📎 Filer vedlagt: {len(files)}")
    print("-" * 80)
    
    current_memory = get_memory()
    log = SYSTEM_PROMPT + f"\n\n=== DINE TIDLIGERE ERFARINGER (AI MEMORY) ===\n{current_memory}\n\nOPPGAVE SOM SKAL LOSES: {prompt}\n"
    
    previous_endpoint = None
    previous_method = None
    loop_counter = 0
    api_res = None
    feil_logg =[]

    # Tillater 30 steg for å sikre at komplekse dataanalyse-oppgaver blir ferdige
    for step in range(30):  
        print(f"[STEG {step+1}] Gemini tenker...")
        try:
            gemini_contents = [log]
            for f in files:
                try:
                    file_bytes = base64.b64decode(f["content_base64"])
                    gemini_contents.append(types.Part.from_bytes(data=file_bytes, mime_type=f["mime_type"]))
                except Exception: pass

            # Bruker 3 Flash for maksimal hastighet
            response = client.models.generate_content(model='gemini-3-flash-preview', contents=gemini_contents)
            raw_text = response.text.strip()
            
            raw_text = raw_text.replace("DU GJORDE:", "").strip()
            # Super-robust JSON extractor
            start_idx = raw_text.find('{')
            end_idx = raw_text.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_text = raw_text[start_idx:end_idx+1]
                action = json.loads(clean_text)
            else:
                raise ValueError("Ingen gyldig JSON funnet")
            
        except Exception as e:
            print(f"[STEG {step+1}][FEIL] Ugyldig JSON.")
            log += "\nFEIL: Svarte ikke med gyldig JSON. Svar KUN med JSON-objektet. Bruk { og }.\n"
            feil_logg.append("Svarte med tekst istedenfor JSON.")
            continue
            
        if action.get("status") == "DONE":
            if step == 0:
                log += "\nFEIL: Du ma starte oppgaven forst.\n"
                continue
            if api_res and api_res.status_code >= 400:
                print(f"[STEG {step+1}] [ADVARSEL] Tvinger fortsettelse pga feil.")
                log += f"\nFEIL: Forrige kall feilet. Du ma fiks feilen for du kan si DONE!\n"
                continue
            print(f"[STEG {step+1}] ✅ SUKSESS! Oppgave fullfort.")
            break
            
        method = action.get("method", "GET").upper()
        raw_endpoint = action.get("endpoint", action.get("url", ""))
        endpoint = re.sub(r'^(GET|POST|PUT|DELETE)\s+', '', raw_endpoint, flags=re.IGNORECASE).strip()
        if not endpoint.startswith("/"): endpoint = "/" + endpoint
            
        if not endpoint:
            log += "\nFEIL: Endpoint mangler. Sjekk JSON-formatet ditt.\n"
            continue
            
        params = action.get("params", {})
        payload = action.get("body", action.get("json", action.get("data", {})))
        
        # --- DEN ULTIMATE VAKTBIKKJA MOT 200-OK LOOPS OG BLINDE SØK ---
        if method == "GET" and not params and any(x in endpoint for x in["account", "invoice", "customer", "employee", "product"]):
            print(f"[STEG {step+1}] 🛑 BLOKKERT: Tomt GET-søk på {endpoint}!")
            log += f"\nFEIL: Du KAN IKKE gjore et tomt GET-sok pa {endpoint}! Du MA sende med parametere (f.eks 'number': '1234' eller 'email'). Hvis sandkassen er tom, OPPRETT det med POST!\n"
            feil_logg.append(f"Gjorde et tomt GET-søk på {endpoint}.")
            continue
            
        url = f"{base_url}{endpoint}"
        body_summary = json.dumps(payload)[:80] + ("..." if len(json.dumps(payload)) > 80 else "")
        print(f" -> KALL: {method} {endpoint} | Params: {params} | Body: {body_summary}")
        
        try:
            if method == "POST": api_res = requests.post(url, auth=auth, params=params, json=payload)
            elif method == "PUT": api_res = requests.put(url, auth=auth, params=params, json=payload)
            elif method == "GET": api_res = requests.get(url, auth=auth, params=params)
            elif method == "DELETE": api_res = requests.delete(url, auth=auth, params=params)
            else: break
            
            # --- TOKEN KILL-SWITCH ---
            if api_res.status_code == 403 and "token" in api_res.text.lower():
                print(f"🚨 [KRITISK] Token utlopt fra Tripletex! Avbryter.")
                break
                
            status_color = "OK" if api_res.status_code < 400 else "FEIL"
            if api_res.status_code in[200, 201]:
                try:
                    res_data = api_res.json()
                    if "value" in res_data and isinstance(res_data["value"], dict) and "id" in res_data["value"]:
                        short_res = f"Suksess! Opprettet/Funnet ID: {res_data['value']['id']}"
                        log += f"\nSUKSESS! Du fikk ID: {res_data['value']['id']}. BRUK DENNE DIREKTE I NESTE KALL!\n"
                    elif "values" in res_data:
                        if len(res_data["values"]) > 0:
                            short_res = f"Fant {len(res_data['values'])} treff. Forste ID: {res_data['values'][0].get('id')}"
                        else:
                            short_res = "0 TREFF! Objektet finnes ikke i sandkassen! DU MA OPPRETTE DET MED POST!"
                    else:
                        short_res = "Suksess (Ingen ID returnert)"
                except:
                    short_res = "Suksess"
            else:
                short_res = api_res.text[:300].replace('\n', ' ')
                
            print(f" -> SVAR:[{status_color} {api_res.status_code}] {short_res}")
            
            # Hvis vi gjør analyse, gi Gemini mye data tilbake (3000 tegn)
            svar_logg = api_res.text[:3000] if "/posting" in endpoint else short_res
            log += f"\nKALLET: {json.dumps(action)}\nSVAR ({api_res.status_code}): {svar_logg}\n"
            
            if api_res.status_code >= 400:
                feil_logg.append(f"Kall: {method} {endpoint}. Body: {json.dumps(payload)}. Feil: {short_res}")
                if endpoint == previous_endpoint and method == previous_method:
                    loop_counter += 1
                if loop_counter >= 2:
                    log += "\nFEIL: LOOP DETECTED! Du gjor samme feil. 'Feltet eksisterer ikke' betyr at du MA fjerne feltet helt fra JSON-en din! Hvis validering feiler, sjekk om du mangler objekt-referanser {id: 123}. Bytt strategi!\n"
                else:
                    log += "FEIL: Les 'validationMessages' i svaret og fiks JSON-bodyen! Referanser ma vaere objekt {id: 123}!\n"
            else:
                # 200 OK Loop Detector
                if endpoint == previous_endpoint and method == previous_method and method == "GET":
                    loop_counter += 1
                    if loop_counter >= 2:
                        log += "\nFEIL: Du gjor AKKURAT det samme GET-soket en gang til selv om det var vellykket! Ga videre til neste API-kall (f.eks POST) for a komme videre i oppgaven!\n"
                else:
                    loop_counter = 0
                log += "Neste steg?\n"
                
            previous_endpoint = endpoint
            previous_method = method
            
        except Exception as e:
            print(f" ->[NETFEIL] {e}")
            break

    # ====================================================================
    # SELF-REFLECTION ENGINE (SKRIVER TIL AI-MINNET)
    # ====================================================================
    if feil_logg:
        print("\n🎓 Agenten oppdaterer AI-minnet (Self-Reflection)...")
        reflection_prompt = f"""Du loste en Tripletex-oppgave, men du gjorde disse feilene underveis:
{json.dumps(feil_logg, indent=2)}

Skriv EN super-kort teknisk regel (maks 1 setning) for a unnga disse feilene neste gang.
Fokuser KUN pa Tripletex API-struktur.
Svar KUN pa formatet: '- HUSK: [Din regel her]'."""
        try:
            lesson_res = client.models.generate_content(model='gemini-3-flash-preview', contents=reflection_prompt)
            save_lesson(lesson_res.text.strip())
        except Exception as e:
            print(f"❌ Klarte ikke a lagre minnet: {e}")

    print("="*80 + "\n")
    return JSONResponse({"status": "completed"})