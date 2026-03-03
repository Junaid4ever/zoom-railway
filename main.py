import asyncio
import random
import base64
import os
import json
from datetime import datetime
import indian_names
from faker import Faker
from playwright.async_api import async_playwright
import nest_asyncio
import firebase_admin
from firebase_admin import credentials, db

nest_asyncio.apply()

# Railway se Firebase creds
firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
if not firebase_creds_json:
    print("❌ FIREBASE_CREDENTIALS environment variable not set!")
    exit(1)

cred_dict = json.loads(firebase_creds_json)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://zoom-bot-controller-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

INSTANCE_ID = f"railway_{os.environ.get('RAILWAY_SERVICE_ID', 'unknown')[:4]}_{random.randint(100,999)}"
fake = Faker('en_US')

def get_name(name_mode="indian"):
    if name_mode == "english":
        gender = random.choice(['male', 'female'])
        return (fake.first_name_male() if gender == 'male' else fake.first_name_female()) + " " + fake.last_name()
    else:
        return indian_names.get_full_name(gender=random.choice(['male', 'female']))

class ZoomBot:
    def __init__(self, instance_id, bot_id, meeting_code, passcode, duration, name_mode="indian"):
        self.instance_id = instance_id
        self.bot_id = bot_id
        self.meeting_code = meeting_code
        self.passcode = passcode
        self.duration = duration
        self.name_mode = name_mode
        self.tag = f"[{instance_id} | Bot {bot_id}]"
        
    async def run(self):
        print(f"{self.tag} Starting...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                page = await browser.new_page()
                
                domain = base64.b64decode('em9vbS51cw==').decode()
                url = f"https://{domain}/wc/join/{self.meeting_code}"
                print(f"{self.tag} Opening {url}")
                await page.goto(url, timeout=60000)
                
                # Name input
                await page.wait_for_selector('xpath=//*[@id="input-for-name"]', timeout=30000)
                await page.fill('xpath=//*[@id="input-for-name"]', get_name(self.name_mode))
                
                # Passcode if needed
                if self.passcode and self.passcode != "skip":
                    try:
                        await page.fill('xpath=//input[@type="password"]', self.passcode)
                    except:
                        pass
                
                # Wait for start signal
                print(f"{self.tag} Waiting for start signal...")
                start_ref = db.reference('commands/global/start_signal')
                while start_ref.get() != "go":
                    await asyncio.sleep(1)
                
                # Join button
                await page.click('xpath=//button[contains(text(), "Join")]')
                print(f"{self.tag} Joined meeting")
                
                # Stay in meeting
                await asyncio.sleep(self.duration * 60)
                await browser.close()
                print(f"{self.tag} Finished")
                
        except Exception as e:
            print(f"{self.tag} Error: {e}")

class RailwayWorker:
    def __init__(self):
        self.instance_id = INSTANCE_ID
        self.bots_running = 0
        print(f"🚀 Railway Worker: {self.instance_id}")
        
    def register(self):
        """Register this instance with Firebase"""
        ref = db.reference(f'instances/{self.instance_id}')
        ref.set({
            'id': self.instance_id,
            'status': 'idle',
            'last_heartbeat': datetime.now().isoformat(),
            'bots_capacity': 5,
            'name_mode': 'indian'
        })
        print(f"✅ Instance {self.instance_id} registered")
        
    def heartbeat(self):
        """Send heartbeat to Firebase"""
        ref = db.reference(f'instances/{self.instance_id}')
        while True:
            ref.update({
                'status': 'busy' if self.bots_running > 0 else 'idle',
                'last_heartbeat': datetime.now().isoformat(),
                'bots_running': self.bots_running
            })
            time.sleep(5)
    
    def listen(self):
        """Listen for commands from controller"""
        ref = db.reference(f'commands/{self.instance_id}')
        while True:
            cmd = ref.get()
            if cmd and cmd.get('action') == 'start_bots':
                print(f"📥 Received: {cmd}")
                # Run bots in new thread
                import threading
                thread = threading.Thread(target=self.run_bots, args=(cmd,))
                thread.start()
            time.sleep(2)
    
    def run_bots(self, cmd):
        """Run bots in separate thread"""
        self.bots_running = cmd.get('count', 1)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        tasks = []
        for i in range(cmd['count']):
            bot = ZoomBot(
                self.instance_id, 
                f"bot_{i}", 
                cmd['meeting'], 
                cmd.get('passcode', 'skip'), 
                cmd.get('duration', 90),
                cmd.get('name_mode', 'indian')
            )
            tasks.append(bot.run())
        
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self.bots_running = 0
    
    def run(self):
        """Main function"""
        self.register()
        
        # Start heartbeat in thread
        import threading
        heartbeat_thread = threading.Thread(target=self.heartbeat)
        heartbeat_thread.daemon = True
        heartbeat_thread.start()
        
        # Start listener in main thread
        self.listen()

if __name__ == "__main__":
    import time
    worker = RailwayWorker()
    worker.run()