import os
import asyncio
import time
import re
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from playwright.async_api import async_playwright
import pyrebase

# 🔒 Admin Key
SECRET_KEY = "Akshay12apidev"

# 🔥 Firebase Configuration (Aapka Naya Project - Alag Database)
firebaseConfig = {
    "apiKey": "AIzaSyDZ_6yr-AI0j2fCDS_lFsR8Gx2ZOjTfN7w",
    "authDomain": "luckymall-23b3f.firebaseapp.com",
    "databaseURL": "https://luckymall-23b3f-default-rtdb.firebaseio.com",
    "projectId": "luckymall-23b3f",
    "storageBucket": "luckymall-23b3f.firebasestorage.app",
    "messagingSenderId": "388214328227",
    "appId": "1:388214328227:web:07534d2887fc90117d6816"
}

# Firebase Initialize (Data will be saved permanently in cloud)
db = None
try:
    firebase = pyrebase.initialize_app(firebaseConfig)
    db = firebase.database()
    print("✅ Firebase Connected Successfully!")
except Exception as e:
    print(f"❌ Firebase Connection Error: {e}")
    db = None

playwright_instance = None
browser = None

# Active Sessions: number -> {"context": context, "page": page, "created_at": time}
active_sessions = {}
sessions_lock = asyncio.Lock()
SESSION_TIMEOUT = 180  # 3 minutes me auto cleanup

# Concurrent Request Control (Server Crash se bachane ke liye)
MAX_CONCURRENT_REQUESTS = 5
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

def get_clean_number(number: str) -> str:
    """Number me se strictly last 10 digits nikalega"""
    digits = re.sub(r'\D', '', str(number or ''))
    return digits[-10:] if len(digits) >= 10 else digits

async def cleanup_loop():
    """Background task: Purane tabs close karke RAM free karta hai"""
    while True:
        await asyncio.sleep(30)
        now = time.time()
        async with sessions_lock:
            expired_numbers = [
                num for num, sess in active_sessions.items()
                if now - sess["created_at"] > SESSION_TIMEOUT
            ]
            for num in expired_numbers:
                sess = active_sessions.pop(num, None)
                if sess:
                    try:
                        await sess["context"].close()
                    except Exception:
                        pass

async def api_cleanup_loop():
    """Background task: Expired API Keys ko auto-delete karta hai"""
    while True:
        await asyncio.sleep(3600)
        if db:
            try:
                apis = db.child("apis").get().val()
                if apis:
                    now = time.time()
                    for api_key, data in apis.items():
                        if data and "expires_at" in data and now > data["expires_at"]:
                            db.child("apis").child(api_key).remove()
                            print(f"🗑️ Auto-deleted expired API: {api_key}")
            except Exception as e:
                print(f"API Cleanup Error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global playwright_instance, browser
    playwright_instance = await async_playwright().start()
    
    browser = await playwright_instance.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--no-first-run",
            "--blink-settings=imagesEnabled=false"
        ]
    )
    cleanup_task = asyncio.create_task(cleanup_loop())
    api_cleanup_task = asyncio.create_task(api_cleanup_loop())
    
    yield
    
    cleanup_task.cancel()
    api_cleanup_task.cancel()
    if browser:
        await browser.close()
    if playwright_instance:
        await playwright_instance.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Server active"}

# =============================================================
# 🔑 API MANAGEMENT SYSTEM (Admin Only)
# =============================================================

@app.get("/create")
async def create_api(key: str = Query(None), day: int = Query(30)):
    if key != SECRET_KEY:
        return {"status": "error", "message": "Unauthorized: Invalid Admin Key"}
    if not db:
        return {"status": "error", "message": "Database not connected."}

    new_api = uuid.uuid4().hex.upper()
    expires_at = time.time() + (day * 86400)
    
    try:
        db.child("apis").child(new_api).set({
            "created_at": time.time(),
            "expires_at": expires_at,
            "days_valid": day,
            "sent_count": 0,
            "verify_count": 0
        })
        return {
            "status": "success", 
            "message": f"API created for {day} days", 
            "api_key": new_api,
            "expires_at": expires_at
        }
    except Exception as e:
        return {"status": "error", "message": f"Database Error: {str(e)}"}

@app.get("/delete")
async def delete_api(key: str = Query(None), api: str = Query(None)):
    if key != SECRET_KEY:
        return {"status": "error", "message": "Unauthorized: Invalid Admin Key"}
    if not db:
        return {"status": "error", "message": "Database not connected."}

    try:
        db.child("apis").child(api).remove()
        return {"status": "success", "message": f"API {api} deleted successfully."}
    except Exception as e:
        return {"status": "error", "message": f"Database Error: {str(e)}"}

@app.get("/check")
async def check_apis(key: str = Query(None)):
    if key != SECRET_KEY:
        return {"status": "error", "message": "Unauthorized: Invalid Admin Key"}
    if not db:
        return {"status": "error", "message": "Database not connected."}

    try:
        apis = db.child("apis").get().val()
        if not apis:
            return {"status": "success", "message": "No APIs found", "apis": {}}
        
        formatted_apis = {}
        for api_key, data in apis.items():
            formatted_apis[api_key] = {
                "sent_count": data.get("sent_count", 0),
                "verify_count": data.get("verify_count", 0),
                "days_valid": data.get("days_valid", 0),
                "expires_in_seconds": max(0, int(data.get("expires_at", 0) - time.time()))
            }
        
        return {"status": "success", "total_apis": len(formatted_apis), "apis": formatted_apis}
    except Exception as e:
        return {"status": "error", "message": f"Database Error: {str(e)}"}

# =============================================================
# STEP 1: SUPERFAST OTP Send Request (New Website)
# =============================================================
@app.get("/sent")
async def sent_otp(api: str = Query(None), number: str = Query(None)):
    if not api:
        return {"status": "error", "message": "API Key is required"}
    if not db:
        return {"status": "error", "message": "Database not connected."}
    
    # API Validation aur Usage Update
    try:
        api_data = db.child("apis").child(api).get().val()
        if not api_data:
            return {"status": "error", "message": "Invalid API Key"}
        if time.time() > api_data.get("expires_at", 0):
            db.child("apis").child(api).remove()
            return {"status": "error", "message": "API Key has expired"}
        db.child("apis").child(api).update({"sent_count": api_data.get("sent_count", 0) + 1})
    except Exception as e:
        return {"status": "error", "message": f"Database Error: {str(e)}"}

    clean_num = get_clean_number(number)
    if not clean_num or len(clean_num) != 10:
        return {"status": "error", "message": "Valid 10-digit mobile number required"}

    async with request_semaphore:
        async with sessions_lock:
            if clean_num in active_sessions:
                try:
                    await active_sessions[clean_num]["context"].close()
                except Exception:
                    pass
                del active_sessions[clean_num]

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 360, "height": 640}
        )
        
        # Speed Booster
        await context.route(
            "**/*",
            lambda route: route.abort() if route.request.resource_type in ["image", "stylesheet", "font", "media"] else route.continue_()
        )
        
        page = await context.new_page()

        try:
            # Oracle APEX URL
            await page.goto("https://prodvbcs-vb-frjvz3maumzj.builder.eu-frankfurt-1.ocp.oraclecloud.com/ic/builder/rt/EmployeeOnboardingApp/live/webApps/web-app/?page=shell&shell=login-page&login-page=otp-login", wait_until="domcontentloaded", timeout=30000)
            
            # Mobile Number Fill
            phone_input = page.locator('input[type="text"], input[type="tel"]').first
            await phone_input.wait_for(state="visible", timeout=15000)
            await phone_input.fill(clean_num, timeout=5000)
            
            # Generate OTP Click
            await page.click('text=Generate OTP', timeout=8000)
            
            # Exact Success Message ka wait karein (Fast Polling)
            await page.wait_for_selector('text=OTP sent to the mobile number', state='visible', timeout=15000)
            
            async with sessions_lock:
                active_sessions[clean_num] = {
                    "context": context,
                    "page": page,
                    "created_at": time.time()
                }
            
            return {"status": "success", "message": f"OTP sent successfully to {clean_num}"}

        except Exception as e:
            await context.close()
            return {"status": "error", "message": f"Automation Error: {str(e)}"}

# =============================================================
# STEP 2: SUPERFAST OTP Verification (New Website)
# =============================================================
@app.get("/verify")
async def verify_otp(api: str = Query(None), number: str = Query(None), otp: str = Query(None)):
    if not api:
        return {"status": "error", "message": "API Key is required"}
    if not db:
        return {"status": "error", "message": "Database not connected."}

    # API Validation aur Usage Update
    try:
        api_data = db.child("apis").child(api).get().val()
        if not api_data:
            return {"status": "error", "message": "Invalid API Key"}
        if time.time() > api_data.get("expires_at", 0):
            db.child("apis").child(api).remove()
            return {"status": "error", "message": "API Key has expired"}
        db.child("apis").child(api).update({"verify_count": api_data.get("verify_count", 0) + 1})
    except Exception as e:
        return {"status": "error", "message": f"Database Error: {str(e)}"}

    clean_num = get_clean_number(number)
    clean_otp = str(otp or "").strip()

    if not clean_num or not clean_otp:
        return {"status": "error", "message": "Both number and otp are required"}

    async with sessions_lock:
        session = active_sessions.pop(clean_num, None)

    if not session:
        return {"status": "error", "message": "Pehle /sent call karein ya session expire ho gaya hai."}

    context = session["context"]
    page = session["page"]

    try:
        # OTP भरें (JS Injection - Fastest & most accurate)
        await page.evaluate("""(otp) => {
            const inputs = document.querySelectorAll('input[type="text"], input[type="tel"]');
            if (inputs.length >= 2) {
                const target = inputs[1]; // Second input is OTP
                target.value = otp;
                target.dispatchEvent(new Event('input', { bubbles: true }));
                target.dispatchEvent(new Event('change', { bubbles: true }));
                target.dispatchEvent(new Event('keyup', { bubbles: true }));
                target.dispatchEvent(new Event('blur', { bubbles: true }));
            }
        }""", clean_otp)

        await asyncio.sleep(0.5) # React state update ke liye thoda wait

        # Login Click
        await page.click('text=Login', timeout=8000)

        # 🚀 SUPERFAST STATUS CHECK (Polling instead of page.content())
        verified_status = "error"
        response_msg = "Galat OTP!"

        for _ in range(40): # Max 6 seconds (0.15s * 40)
            # 1. Error Check
            if await page.locator('text=Invalid OTP Entered').count() > 0:
                verified_status = "error"
                response_msg = "Galat OTP!"
                break
            
            # 2. QR Code Check (Success)
            if await page.locator('text=Please Scan the QR').count() > 0:
                verified_status = "success"
                response_msg = "OTP verified successfully! (QR Scan Required)"
                break

            # 3. Login Success Check
            if await page.locator('text=Dashboard').count() > 0 or await page.locator('text=Logout').count() > 0 or await page.locator('text=Welcome').count() > 0:
                verified_status = "success"
                response_msg = "OTP verified and login successful!"
                break

            await asyncio.sleep(0.15) # Fast Polling

        await context.close()
        return {"status": verified_status, "message": response_msg}

    except Exception as e:
        try:
            await context.close()
        except:
            pass
        return {"status": "error", "message": f"Automation Error: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)